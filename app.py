#!/usr/bin/env python3
"""
UAV-LLM: Semantic Multi-Commodity UAV Delivery System
FastAPI backend — MPDD + HNP algorithms + Ollama GLM4 integration
"""

import math, time, itertools, random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import httpx, json, os

app = FastAPI(title="UAV-LLM System", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

CLASSES = ["PHARMA","FOOD","ELECTRONICS","FLAMMABLE","OXIDIZER","CRYOGENIC","GENERAL"]
HAZARD_CLASSES = {"FLAMMABLE","OXIDIZER","CRYOGENIC"}
FIXED_INCOMPAT = [("FLAMMABLE","OXIDIZER"),("CRYOGENIC","ELECTRONICS"),
                  ("FLAMMABLE","PHARMA"),("OXIDIZER","PHARMA"),("CRYOGENIC","FOOD"),
                  ("FLAMMABLE","FOOD"),("OXIDIZER","FOOD")]
PENALTIES = {"compat":220.0,"geo":160.0,"payload":300.0,"precedence":220.0,"missed":600.0}
ALPHA = {"distance":1.0,"lateness":1.8,"noise":0.55,"energy":0.08}
OLLAMA_URL = os.getenv("OLLAMA_URL","http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL","glm4")
UAV_SPEED  = 15.0
ROTOR_K    = 0.04
MIN_ALT    = 20.0
CLEARANCE  = 8.0

@dataclass
class Package:
    idx: int
    pickup_loc: int
    delivery_loc: int
    weight: float
    kappa: str
    deadline: float
    priority: float
    temp_required: bool
    description: str = ""

@dataclass
class GeoZone:
    x: float; y: float; radius: float
    kind: str
    label: str = ""
    alt_min: float = 0.0
    alt_max: float = 9999.0

@dataclass
class CityNode:
    idx: int
    x: float; y: float
    building_height: float
    label: str
    is_depot: bool = False
    pickups: List[dict] = field(default_factory=list)
    drops:   List[dict] = field(default_factory=list)

def d2(a, b) -> float:
    return float(np.linalg.norm(np.array([a[0]-b[0], a[1]-b[1]])))

def d3(a, b) -> float:
    return float(np.linalg.norm(np.array(a) - np.array(b)))

def build_compat(density: float, seed: int) -> Dict[Tuple,bool]:
    rng = np.random.default_rng(seed)
    G = {(a,b): True for a in CLASSES for b in CLASSES}
    for a,b in FIXED_INCOMPAT:
        G[(a,b)] = G[(b,a)] = False
    pairs = [(a,b) for i,a in enumerate(CLASSES) for b in CLASSES[i+1:]]
    for a,b in pairs:
        if G[(a,b)] and rng.random() < density:
            G[(a,b)] = G[(b,a)] = False
    return G

def clique_ok(classes: list, G: dict) -> bool:
    return all(G.get((a,b), True) for a,b in itertools.combinations(classes, 2))

def seg_hits_zone(ax,ay, bx,by, z: GeoZone) -> bool:
    cx,cy = z.x, z.y
    abx,aby = bx-ax, by-ay
    denom = abx*abx + aby*aby
    if denom < 1e-12:
        return (ax-cx)**2+(ay-cy)**2 <= z.radius**2
    t = max(0.0, min(1.0, ((cx-ax)*abx+(cy-ay)*aby)/denom))
    px,py = ax+t*abx, ay+t*aby
    return (px-cx)**2+(py-cy)**2 <= z.radius**2

def required_alt(traj_nodes, i, j, city_nodes) -> float:
    ai, bi = traj_nodes[i], traj_nodes[j]
    x0,x1 = min(ai[0],bi[0])-5, max(ai[0],bi[0])+5
    y0,y1 = min(ai[1],bi[1])-5, max(ai[1],bi[1])+5
    max_bh = max((n.building_height for n in city_nodes if x0<=n.x<=x1 and y0<=n.y<=y1), default=0.0)
    return max(MIN_ALT, max_bh + CLEARANCE)

def energy(dist: float, payload: float) -> float:
    return dist * (1.0 + ROTOR_K * payload)

def dist_2d(a,b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def wind_penalty(ax,ay,bx,by, wind_dir: float=45.0, wind_speed: float=5.0) -> float:
    dx,dy = bx-ax, by-ay
    seg_angle = math.degrees(math.atan2(dy,dx)) % 360
    diff = abs(seg_angle - wind_dir) % 360
    if diff > 180: diff = 360 - diff
    headwind_factor = math.cos(math.radians(diff))
    return dist_2d([ax,ay],[bx,by]) * max(0, headwind_factor) * wind_speed * 0.002

def node_role(node: int, n: int):
    if 1 <= node <= n:    return "P", node-1
    if n+1<=node<=2*n:    return "D", node-(n+1)
    return "DEPOT", -1

def evaluate(traj_xy, packages, route, G, gzones, nzones, synth=None, W=20.0, wind_dir=45.0, battery_cap=50000.0):
    n = len(packages)
    onboard=set(); delivered=set(); y=0.0; t=0.0; bat=battery_cap
    dist=en=noise=lateness=bat_over=0.0
    cv=gv=pv=rv=0; seen=set()
    for s in range(len(route)-1):
        u,v = route[s], route[s+1]
        ax,ay = traj_xy[u]; bx,by = traj_xy[v]
        seg = dist_2d([ax,ay],[bx,by]); dist += seg
        e_seg = energy(seg, y) + wind_penalty(ax,ay,bx,by,wind_dir)
        en += e_seg; bat -= e_seg
        if bat < 0: bat_over += 1
        noise += sum(seg for z in nzones if seg_hits_zone(ax,ay,bx,by,z))
        if any(seg_hits_zone(ax,ay,bx,by,z) for z in gzones): gv += 1
        t += seg / UAV_SPEED
        tp, rid = node_role(v, n)
        if tp in {"P","D"}:
            if v in seen: rv += 1
            seen.add(v)
        if tp=="P":
            pkg=packages[rid]; y+=pkg.weight; onboard.add(rid)
        elif tp=="D":
            pkg=packages[rid]
            if rid not in onboard: rv += 1
            else: y-=pkg.weight; onboard.remove(rid); delivered.add(rid)
            lateness += max(0, t-pkg.deadline)*pkg.priority
        if y<-1e-6 or y-W>1e-6: pv += 1
        kk=[( synth[i] if synth else packages[i].kappa) for i in onboard]
        if not clique_ok(kk, G): cv += 1
    missed = len(set(range(1,2*n+1))-seen)+len(seen-set(range(1,2*n+1)))+rv
    if not(route and route[0]==0 and route[-1]==2*n+1): missed+=1
    total_viol = cv+gv+pv+rv+missed
    cost = (ALPHA["distance"]*dist + ALPHA["lateness"]*lateness + ALPHA["noise"]*noise + ALPHA["energy"]*en + PENALTIES["compat"]*cv + PENALTIES["geo"]*gv + PENALTIES["payload"]*pv + PENALTIES["precedence"]*rv + PENALTIES["missed"]*missed)
    return {"cost":cost,"dist":dist,"lateness":lateness,"noise":noise,"energy":en,"cv":cv,"gv":gv,"pv":pv,"rv":rv,"missed":missed,"viol":total_viol,"feasible":total_viol==0,"delivered":len(delivered),"n":n,"time":t,"battery_ok":bat_over==0}

def blocks_future(rid, onboard, U, synth, packages, G, n):
    if rid not in onboard: return 0
    before=[synth[i] for i in onboard]; after=[synth[i] for i in onboard if i!=rid]
    for uk in U:
        utp, uid = node_role(uk, n)
        if utp=="P":
            ck = synth[uid]
            if not clique_ok(before+[ck],G) and clique_ok(after+[ck],G): return 1
    return 0

def hnp_scores(traj_xy, packages, cands, cur, onboard, U, synth, G, gzones, t, n, beta=45.0, gamma_geo=1.5, gamma_dl=120.0):
    cpos = traj_xy[cur]
    dists = {j: max(1e-6, dist_2d(cpos, traj_xy[j])) for j in cands}
    dmin = min(dists.values())
    out = {}
    for j in cands:
        tp, rid = node_role(j, n)
        if rid < 0: continue
        pkg = packages[rid]; d = dists[j]
        dl = gamma_dl*pkg.priority/max(1.0,pkg.deadline-t) if tp=="D" else 0
        geo = gamma_geo*sum(1 for z in gzones if seg_hits_zone(*cpos,*traj_xy[j],z))
        blk = beta*blocks_future(rid,onboard,U,synth,packages,G,n) if tp=="D" else 0
        out[j] = 0.55*(dmin/d) + 0.45*pkg.weight + blk + dl - geo
    return out

def mpdd_scores(traj_xy, packages, cands, cur, n):
    cpos = traj_xy[cur]
    dists = {j:max(1e-6,dist_2d(cpos,traj_xy[j])) for j in cands}
    dmin=min(dists.values())
    vals={j:packages[node_role(j,n)[1]].weight if node_role(j,n)[1]>=0 else 1. for j in cands}
    vm=max(vals.values(),default=1.)
    return {j:0.6*(dmin/dists[j])+0.4*(vals[j]/vm) for j in cands}

def nn_scores(traj_xy, cands, cur):
    cpos = traj_xy[cur]
    dists = {j:max(1e-6,dist_2d(cpos,traj_xy[j])) for j in cands}
    dmin=min(dists.values())
    return {j:dmin/dists[j] for j in cands}

def feasible_cands(packages, traj_xy, route, U, onboard, y, synth, G, W, compat_check):
    n=len(packages); C=[]; active=[synth[i] for i in onboard]
    for node in U:
        tp,rid = node_role(node,n)
        if tp=="P":
            pkg=packages[rid]
            if y+pkg.weight<=W+1e-9:
                kk=synth[rid]
                if (not compat_check) or clique_ok(active+[kk],G): C.append(node)
        elif tp=="D" and rid in onboard: C.append(node)
    return C

def build_route(packages, traj_xy, synth, G, gzones, W, compat_check, score_fn, label):
    n=len(packages); start=0; end=2*n+1
    route=[start]; U=set(range(1,2*n+1)); onboard=set(); y=0.0; t=0.0; log=[]
    for _ in range(20*(2*n+2)):
        if not U: break
        C=feasible_cands(packages,traj_xy,route,U,onboard,y,synth,G,W,compat_check)
        if not C:
            unpicked=[j for j in U if node_role(j,n)[0]=="P"]
            if not unpicked: break
            C=unpicked
        if not C: break
        sc = score_fn(C, route[-1], onboard, U, t)
        jstar=max(C, key=lambda j:sc.get(j,0))
        log.append({"algo":label,"node":jstar,"score":round(sc.get(jstar,0),3),"candidates":len(C),"onboard":len(onboard),"payload":round(y,2)})
        prev=route[-1]; route.append(jstar)
        t += dist_2d(traj_xy[prev],traj_xy[jstar])/UAV_SPEED
        tp,rid=node_role(jstar,n)
        if tp=="P": onboard.add(rid); y+=packages[rid].weight
        elif tp=="D" and rid in onboard: onboard.remove(rid); y-=packages[rid].weight
        U.discard(jstar)
    if route[-1]!=end: route.append(end)
    return route, log

def refine(packages, traj_xy, route, synth, G, W, gzones, max_passes=3):
    best=route[:]; n=len(packages)
    def pick_pos(rt): return [i for i,nd in enumerate(rt) if node_role(nd,n)[0]=="P"]
    for _ in range(max_passes):
        improved=False
        anchors=[0]+pick_pos(best)+[len(best)-1]
        for ai in range(len(anchors)-1):
            lo,hi=anchors[ai],anchors[ai+1]
            if hi-lo<=3: continue
            seg=best[lo+1:hi]; dloc=[k for k,nd in enumerate(seg) if node_role(nd,n)[0]=="D"]
            if len(dloc)<2: continue
            base=evaluate(traj_xy,packages,best,G,[],[],synth,W)["dist"]
            for xi in range(len(dloc)):
                for yi in range(xi+1,len(dloc)):
                    cand=best[:]; ix,iy=lo+1+dloc[xi],lo+1+dloc[yi]
                    cand[ix],cand[iy]=cand[iy],cand[ix]
                    m=evaluate(traj_xy,packages,cand,G,[],[],synth,W)
                    if m["dist"]<base-1e-9 and m["pv"]==0 and m["rv"]==0:
                        best=cand; improved=True; break
                if improved: break
            if improved: break
        if not improved: break
    return best

CITY_NAMES=["Depot","Hospital Alpha","Warehouse Beta","Pharmacy Gamma","Airport Delta","Mall Epsilon","Fire HQ","Research Lab","University","Hotel Zeta","Market","Police HQ","Stadium","Park North","Port Omega","Data Center","Factory Sigma","Clinic East","Library","Suburb Node"]

def generate_world(n_locs:int, n_pkg:int, seed:int, incompat_density:float, n_gfz:int, deadline_tight:float, hazard_mix:float, cap_ratio:float):
    rng = np.random.default_rng(seed)
    city=[]; city.append(CityNode(0, 50.0, 50.0, 5.0, "Depot", is_depot=True))
    for i in range(n_locs):
        x=float(rng.uniform(8,92)); y=float(rng.uniform(8,92))
        bh=float(rng.choice([8,12,18,25,35,50,60,4,6], p=[0.15,0.15,0.15,0.15,0.12,0.08,0.05,0.1,0.05]))
        city.append(CityNode(i+1,x,y,bh,CITY_NAMES[i+1] if i+1<len(CITY_NAMES) else f"Node {i+1}"))
    G = build_compat(incompat_density, seed)
    def sample_kappa():
        if rng.random()<hazard_mix:
            return rng.choice(["PHARMA","FLAMMABLE","OXIDIZER","CRYOGENIC","ELECTRONICS"], p=[0.30,0.22,0.18,0.15,0.15]).item()
        return rng.choice(CLASSES, p=[0.16,0.18,0.16,0.08,0.06,0.06,0.30]).item()
    pkgs=[]; total_w=0.0
    pkg_labels={"PHARMA":"Insulin","FOOD":"Food Box","ELECTRONICS":"Laptop","FLAMMABLE":"Fuel Can","OXIDIZER":"O₂ Tank","CRYOGENIC":"Cryo Sample","GENERAL":"Package"}
    for i in range(n_pkg):
        kappa=sample_kappa(); pi=rng.integers(1,n_locs+1).item(); di=rng.integers(1,n_locs+1).item()
        while di==pi: di=rng.integers(1,n_locs+1).item()
        w=float(rng.uniform(1.0,6.0)); total_w+=w
        pc=city[pi]; dc=city[di]; dd=dist_2d([pc.x,pc.y],[dc.x,dc.y]); depot_leg=dist_2d([city[0].x,city[0].y],[pc.x,pc.y])+dd
        slack=rng.uniform(30,110)*(1.05-deadline_tight); dl=depot_leg/UAV_SPEED + slack + rng.uniform(0,20)
        pr=1.8 if kappa=="PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
        desc=f"{pkg_labels.get(kappa,'Package')} · {city[pi].label} → {city[di].label}"
        pkgs.append(Package(i,pi,di,w,kappa,float(dl),pr,kappa in {"PHARMA","FOOD","CRYOGENIC"},desc))
        city[pi].pickups.append({"req":i,"kappa":kappa,"w":round(w,2),"label":pkg_labels.get(kappa,"Package")})
        city[di].drops.append({"req":i,"kappa":kappa,"w":round(w,2),"label":pkg_labels.get(kappa,"Package")})
    W_cap=max(8.0, cap_ratio*total_w)
    gzones=[GeoZone(float(rng.uniform(10,85)),float(rng.uniform(10,85)),float(rng.uniform(6,14)),"nofly",f"No-Fly {i+1}") for i in range(n_gfz)]
    nzones=[GeoZone(float(rng.uniform(10,90)),float(rng.uniform(10,90)),float(rng.uniform(8,18)),"noise",f"Noise Zone {i+1}") for i in range(n_gfz)]
    traj_xy=[(city[0].x,city[0].y)]
    for p in pkgs: traj_xy.append((city[p.pickup_loc].x,city[p.pickup_loc].y))
    for p in pkgs: traj_xy.append((city[p.delivery_loc].x,city[p.delivery_loc].y))
    traj_xy.append((city[0].x,city[0].y))
    return city, pkgs, G, gzones, nzones, W_cap, traj_xy

def run_all_algos(pkgs, traj_xy, G, gzones, nzones, W_cap, seed, wind_dir=45.0, llm_error=0.10):
    rng=np.random.default_rng(seed+1); synth_true={p.idx:p.kappa for p in pkgs}
    def make_synth_noisy(err):
        s={}
        for p in pkgs: s[p.idx]=rng.choice([c for c in CLASSES if c!=p.kappa]).item() if rng.random()<err else p.kappa
        return s
    synth_noisy=make_synth_noisy(llm_error); results={}; n=len(pkgs)
    def hnp_sf(C,cur,onboard,U,t): return hnp_scores(traj_xy,pkgs,C,cur,onboard,U,synth_true,G,gzones,t,n)
    r,log=build_route(pkgs,traj_xy,synth_true,G,gzones,W_cap,True,hnp_sf,"HNP"); r=refine(pkgs,traj_xy,r,synth_true,G,W_cap,gzones)
    results["HNP"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_true,W_cap,wind_dir)}
    def mpdd_sf(C,cur,onboard,U,t): return mpdd_scores(traj_xy,pkgs,C,cur,n)
    r,log=build_route(pkgs,traj_xy,synth_true,G,gzones,W_cap,False,mpdd_sf,"MPDD")
    results["MPDD"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_true,W_cap,wind_dir)}
    def nn_sf(C,cur,onboard,U,t): return nn_scores(traj_xy,C,cur)
    r,log=build_route(pkgs,traj_xy,synth_true,G,gzones,W_cap,False,nn_sf,"NN-PDP")
    results["NN-PDP"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_true,W_cap,wind_dir)}
    def hnp_nv_sf(C,cur,onboard,U,t): return hnp_scores(traj_xy,pkgs,C,cur,onboard,U,synth_noisy,G,gzones,t,n)
    r,log=build_route(pkgs,traj_xy,synth_noisy,G,gzones,W_cap,True,hnp_nv_sf,"HNP-NoVerify")
    results["HNP-NoVerify"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_noisy,W_cap,wind_dir)}
    def hnp_nc_sf(C,cur,onboard,U,t): return hnp_scores(traj_xy,pkgs,C,cur,onboard,U,synth_true,G,gzones,t,n)
    r,log=build_route(pkgs,traj_xy,synth_true,G,gzones,W_cap,False,hnp_nc_sf,"HNP-NoCompat")
    results["HNP-NoCompat"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_true,W_cap,wind_dir)}
    def hnp_nr_sf(C,cur,onboard,U,t): return hnp_scores(traj_xy,pkgs,C,cur,onboard,U,synth_true,G,gzones,t,n)
    r,log=build_route(pkgs,traj_xy,synth_true,G,gzones,W_cap,True,hnp_nr_sf,"HNP-NoRefine")
    results["HNP-NoRefine"]={"route":r,"log":log,"metrics":evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth_true,W_cap,wind_dir)}
    return results

async def ollama_chat(prompt:str)->str:
    try:
        async with httpx.AsyncClient(timeout=25.0) as cli:
            r=await cli.post(f"{OLLAMA_URL}/api/generate", json={"model":OLLAMA_MODEL,"prompt":prompt,"stream":False,"options":{"temperature":0.1,"num_predict":600}})
            if r.status_code==200: return r.json().get("response","")
    except Exception as e:
        return f"[LLM offline — {e}]"
    return ""

async def llm_parse_constraint(desc:str)->dict:
    prompt=f"""You are a UAV delivery semantic parser. Extract structured constraints.
Commodity classes: PHARMA, FOOD, ELECTRONICS, FLAMMABLE, OXIDIZER, CRYOGENIC, GENERAL
Hazardous: FLAMMABLE, OXIDIZER, CRYOGENIC
Input: \"{desc}\"
Output ONLY valid JSON (no prose):
{{"kappa":"PHARMA","temp_sensitive":true,"priority":1.8,"deadline_minutes":60,"avoid_zones":["residential"],"incompatible_with":["FLAMMABLE","OXIDIZER"]}}"""
    raw=await ollama_chat(prompt)
    try:
        s=raw.find("{"); e=raw.rfind("}")+1
        if s>=0 and e>s: return json.loads(raw[s:e])
    except: pass
    dl=desc.lower(); kappa="GENERAL"
    if any(w in dl for w in ["insulin","pharma","medicine","drug","vaccine","hospital"]): kappa="PHARMA"
    elif any(w in dl for w in ["fuel","gasoline","flammable"]): kappa="FLAMMABLE"
    elif any(w in dl for w in ["oxygen","oxidizer","o2"]): kappa="OXIDIZER"
    elif any(w in dl for w in ["cryo","liquid nitrogen","freeze"]): kappa="CRYOGENIC"
    elif any(w in dl for w in ["food","meal","grocery","bread"]): kappa="FOOD"
    elif any(w in dl for w in ["laptop","phone","drone","circuit","chip"]): kappa="ELECTRONICS"
    pr=1.8 if kappa=="PHARMA" else (1.4 if kappa in HAZARD_CLASSES else 1.0)
    return {"kappa":kappa,"temp_sensitive":kappa in {"PHARMA","FOOD","CRYOGENIC"},"priority":pr,"deadline_minutes":0,"avoid_zones":[],"incompatible_with":[]}

async def llm_mid_flight(instruction:str, state:dict, node_labels:list)->dict:
    prompt=f"""UAV mission controller. Drone mid-flight.
State: pos={state.get('pos','?')}, payload={state.get('payload',0):.1f}kg, onboard={state.get('onboard',[])}
Nodes available: {node_labels[:12]}
Operator instruction: \"{instruction}\"
Respond ONLY with JSON:
{{"action":"REROUTE|ABORT_PACKAGE|ADD_STOP|EMERGENCY_RETURN|ALTITUDE_CHANGE|STATUS_QUERY","target_node_label":"Hospital Alpha","package_idx":0,"new_altitude":50,"reason":"operator override"}}"""
    raw=await ollama_chat(prompt)
    try:
        s=raw.find("{"); e=raw.rfind("}")+1
        if s>=0 and e>s: return json.loads(raw[s:e])
    except: pass
    return {"action":"STATUS_QUERY","reason":raw[:200] if raw else "No LLM response"}

SESSIONS = {}
class GenConfig(BaseModel):
    n_locs: int=8; n_pkg: int=5; seed: int=42; incompat_density: float=0.25; n_gfz: int=4; deadline_tight: float=0.65; hazard_mix: float=0.5; cap_ratio: float=0.35; wind_dir: float=45.0; llm_error: float=0.10
class LLMParseReq(BaseModel): description: str
class MidFlightReq(BaseModel): instruction: str; session_id: str="default"
class ReplanReq(BaseModel): session_id: str; disruption: dict

@app.get("/")
async def root(): return FileResponse("index.html")

@app.post("/api/generate")
async def generate(cfg: GenConfig):
    city, pkgs, G, gzones, nzones, W_cap, traj_xy = generate_world(cfg.n_locs, cfg.n_pkg, cfg.seed, cfg.incompat_density, cfg.n_gfz, cfg.deadline_tight, cfg.hazard_mix, cfg.cap_ratio)
    results = run_all_algos(pkgs, traj_xy, G, gzones, nzones, W_cap, cfg.seed, cfg.wind_dir, cfg.llm_error)
    sid = f"s{cfg.seed}_{int(time.time()*1000)%100000}"
    SESSIONS[sid] = dict(city=city,pkgs=pkgs,G=G,gzones=gzones,nzones=nzones,W_cap=W_cap,traj_xy=traj_xy,results=results,wind_dir=cfg.wind_dir)
    hnp_route = results["HNP"]["route"]; steps=[]
    for si,nd in enumerate(hnp_route):
        tp,rid=node_role(nd,len(pkgs)); xy=traj_xy[nd]
        alt=required_alt(traj_xy,nd,hnp_route[min(si+1,len(hnp_route)-1)],city) if si<len(hnp_route)-1 else MIN_ALT
        steps.append({"step":si,"node":nd,"x":xy[0],"y":xy[1],"alt":round(alt,1),"type":tp,"req":rid})
    incompat_pairs=[[a,b] for (a,b),ok in G.items() if not ok and a<b]
    return {"session_id": sid,"city": [{"idx":n.idx,"x":n.x,"y":n.y,"bh":n.building_height,"label":n.label,"depot":n.is_depot,"pickups":n.pickups,"drops":n.drops} for n in city],"packages": [{"idx":p.idx,"pickup":p.pickup_loc,"delivery":p.delivery_loc,"weight":round(p.weight,2),"kappa":p.kappa,"deadline":round(p.deadline,1),"priority":p.priority,"temp":p.temp_required,"desc":p.description} for p in pkgs],"gzones": [{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label} for z in gzones],"nzones": [{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label} for z in nzones],"W_cap": round(W_cap,2),"traj_xy": traj_xy,"results": {k: {"route":v["route"],"metrics":v["metrics"],"log":v["log"][:30]} for k,v in results.items()},"hnp_steps": steps,"incompat_pairs": incompat_pairs,"classes": CLASSES,"wind_dir": cfg.wind_dir}

@app.post("/api/llm/parse")
async def llm_parse(req: LLMParseReq):
    result = await llm_parse_constraint(req.description)
    return {"description":req.description,"synthesis":result}

@app.post("/api/llm/midflight")
async def mid_flight(req: MidFlightReq):
    sess=SESSIONS.get(req.session_id,{})
    city=sess.get("city",[]); state={"pos":"en-route","payload":0,"onboard":[]}; labels=[f'{n.idx}:{n.label}' for n in city]
    result=await llm_mid_flight(req.instruction,state,labels)
    return {"instruction":req.instruction,"action":result}

@app.post("/api/replan")
async def replan(req: ReplanReq):
    sess=SESSIONS.get(req.session_id)
    if not sess: raise HTTPException(404,"Session not found")
    disruption=req.disruption
    if disruption.get("type")=="nofly": sess["gzones"].append(GeoZone(disruption["x"],disruption["y"],disruption.get("r",12),"nofly","Emergency Zone"))
    pkgs=sess["pkgs"]; traj_xy=sess["traj_xy"]; G=sess["G"]; gzones=sess["gzones"]; nzones=sess["nzones"]; W_cap=sess["W_cap"]
    synth={p.idx:p.kappa for p in pkgs}
    def hnp_sf(C,cur,onboard,U,t): return hnp_scores(traj_xy,pkgs,C,cur,onboard,U,synth,G,gzones,t,len(pkgs))
    r,log=build_route(pkgs,traj_xy,synth,G,gzones,W_cap,True,hnp_sf,"HNP-Replan"); r=refine(pkgs,traj_xy,r,synth,G,W_cap,gzones)
    m=evaluate(traj_xy,pkgs,r,G,gzones,nzones,synth,W_cap,sess.get("wind_dir",45))
    return {"new_route":r,"metrics":m,"log":log[:20],"new_gzones":[{"x":z.x,"y":z.y,"r":z.radius,"kind":z.kind,"label":z.label} for z in gzones]}

@app.get("/api/compat")
async def compat_graph(density:float=0.25,seed:int=42):
    G=build_compat(density,seed); edges=[{"src":a,"tgt":b,"ok":ok} for (a,b),ok in G.items() if a<b]
    return {"classes":CLASSES,"edges":edges,"fixed":[list(p) for p in FIXED_INCOMPAT]}

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2.0) as cli:
            r=await cli.get(f"{OLLAMA_URL}/api/tags"); ok=r.status_code==200; models=[m["name"] for m in r.json().get("models",[])] if ok else []
    except: ok=False; models=[]
    return {"status":"ok","ollama":ok,"model":OLLAMA_MODEL,"models":models,"sessions":len(SESSIONS)}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=8000,reload=False)

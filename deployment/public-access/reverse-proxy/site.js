"use strict";
const root=document.querySelector('#content'),API='/dragon/api/v1';
function node(tag,text,attrs={}){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;}
function link(text,path){let u;try{u=new URL(path,location.origin);}catch{return node('span',text);}if(!['http:','https:'].includes(u.protocol))return node('span',text);return node('a',text,{href:u.href});}
async function get(path,view){
 const c=new AbortController(),abort=()=>c.abort(),t=setTimeout(abort,15000);
 view.signal.addEventListener('abort',abort,{once:true});
 try{const r=await fetch(API+path,{signal:c.signal,credentials:'omit'});const d=await r.json();if(!r.ok)throw Error(d.error?.message||'Public source unavailable');return d;}
 catch(e){if(e.name==='AbortError'&&!view.signal.aborted)throw Error('The public server did not respond within 15 seconds. Please retry.');throw e;}
 finally{clearTimeout(t);view.signal.removeEventListener('abort',abort);}
}
function section(title){const e=node('section');e.append(node('h2',title));root.append(e);return e;}
function meta(m){return `${m.competition} · ${m.event_date} · ${m.status} · ${m.data_state}`;}
function card(m){const a=node('article');a.append(link(`${m.home.name} vs ${m.away.name}`,`/sports/matches/${m.id}`),node('p',meta(m),{class:'muted'}),node('strong',m.score?`${m.score.home} – ${m.score.away}`:'Result not supplied'));return a;}
let offset=0,search='',generation=0,activeController=null;
function current(view){return view.generation===generation&&!view.signal.aborted;}
async function matches(view){root.replaceChildren(node('h1','DRAGONHYDRA public matches'),node('p','Browse actual retained public fixtures and results. This gateway offers read-only access.'));
 const toolbar=node('form',undefined,{class:'toolbar'}),input=node('input',undefined,{type:'search',placeholder:'Team name','aria-label':'Search teams'});input.value=search;toolbar.append(input,node('button','Search',{type:'submit'}));toolbar.addEventListener('submit',e=>{e.preventDefault();search=input.value;offset=0;show();});root.append(toolbar);
 const d=await get(`/matches?limit=24&offset=${offset}&search=${encodeURIComponent(search)}`,view);if(!current(view))return;root.append(node('p',`${d.total} retained fixtures · date-only kickoff precision`,{class:'muted'}));const cards=node('div',undefined,{class:'cards'});d.items.forEach(m=>cards.append(card(m)));root.append(cards);if(!d.items.length)root.append(node('p','No retained fixtures match this filter.'));
 const paging=node('div',undefined,{class:'toolbar'});for(const[label,change,enabled]of[['Previous',-24,offset>0],['Next',24,offset+24<d.total]]){if(enabled){const b=node('button',label);b.addEventListener('click',()=>{offset+=change;show();});paging.append(b);}}root.append(paging);}
async function match(id,view){const m=await get('/matches/'+id,view);if(!current(view))return;root.replaceChildren(link('← Match library','/sports'),node('h1',`${m.home.name} vs ${m.away.name}`),node('p',meta(m)),node('h2',m.score?`${m.score.home} – ${m.score.away}`:'Scheduled · result not supplied'));
 const c=section('Teams and competition');c.append(link(m.home.name,`/sports/teams/${m.home.id}`),node('span',' · '),link(m.away.name,`/sports/teams/${m.away.id}`),node('p'),link('Open standings',`/sports/competitions/${m.competition_id}`));
 const details=section('Source and timing');details.append(node('p','Source: '+m.source_id),node('p','Source event date: '+m.event_date+'; UTC kickoff/timezone not verified.'),node('p','Locally usable: '+m.usable_at),link('Original public source',m.source_url));
 const context=section('Lineups, statistics and odds');context.append(node('p','This public source does not provide lineups, injuries or player statistics. No approved compatible odds are mapped to this event. Missing information is not a zero.'));
 const forecast=section('Statistical model probabilities');const p=await get(`/matches/${id}/predictions`,view);if(!current(view))return;if(p.available&&p.ensemble){forecast.append(node('p',`Home ${(100*p.ensemble.home).toFixed(1)}% · Draw ${(100*p.ensemble.draw).toFixed(1)}% · Away ${(100*p.ensemble.away).toFixed(1)}%`,{class:'probability'}));forecast.append(node('p',p.interpretation),node('p',`Evidence cutoff: ${p.cutoff}`));}else forecast.append(node('p',p.reason||'No retained forecast is available.'));}
async function team(id,view){const d=await get('/teams/'+id,view);if(!current(view))return;root.replaceChildren(link('← Match library','/sports'),node('h1',d.name));const f=section('Recent form');f.append(node('p',d.form.map(r=>r.result).join(' · ')||'No retained results'));d.unknowns.forEach(s=>f.append(node('p',s,{class:'muted'})));const g=section('Fixtures and results');d.matches.slice(0,40).forEach(m=>g.append(card(m)));}
async function standings(id,view){const d=await get(`/competitions/${id}/standings`,view);if(!current(view))return;root.replaceChildren(link('← Match library','/sports'),node('h1',d.competition),node('p',d.label+' · Unofficial reconstructed table'));const wrap=node('div',undefined,{class:'table-scroll'}),table=node('table'),head=node('tr');for(const h of['Team','Played','Won','Drawn','Lost','GF','GA','Points'])head.append(node('th',h,{scope:'col'}));table.append(head);d.items.forEach(r=>{const tr=node('tr'),td=node('td');td.append(link(r.team,`/sports/teams/${r.team_id}`));tr.append(td);for(const k of['played','won','drawn','lost','goals_for','goals_against','points'])tr.append(node('td',r[k]));table.append(tr);});wrap.append(table);root.append(wrap);d.limitations.forEach(s=>root.append(node('p',s,{class:'muted'})));}
async function show(){
 const ownGeneration=++generation;
 if(activeController)activeController.abort();
 activeController=new AbortController();
 const view={generation:ownGeneration,signal:activeController.signal};
 try{const parts=location.pathname.split('/').filter(Boolean);if(parts.length===1)await matches(view);else if(parts[1]==='matches')await match(parts[2],view);else if(parts[1]==='teams')await team(parts[2],view);else if(parts[1]==='competitions')await standings(parts[2],view);}
 catch(e){if(!current(view))return;root.replaceChildren(node('h1','Sports data is temporarily unavailable'),node('p',e.message));const b=node('button','Retry');b.addEventListener('click',show);root.append(b);}
}
document.addEventListener('click',e=>{const a=e.target.closest('a');if(a&&a.origin===location.origin&&a.pathname.startsWith('/sports')){e.preventDefault();history.pushState({},'',a.href);show();window.scrollTo(0,0);}});window.addEventListener('popstate',show);show();

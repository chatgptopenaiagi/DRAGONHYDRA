/* DRAGONHYDRA dashboard: all calculations and writes belong to the kernel. */
"use strict";
const API = "/dragon/api/v1";
const main = document.querySelector("#main");
const state = {route:"", previous:"#history", match:null, tab:"overview", date:localDay(), search:"", competition:"", offset:0, limit:25, render:0, authenticated:false, stream:null, activeJob:null, scrolls:new Map(), lastHash:location.hash||"#today"};
const navItems = [["live","◉","Live"],["today","▦","Today"],["teams","♧","Teams"],["competitions","◇","Competitions"],["odds","↗","Odds"],["analysis","◫","Analysis"],["research","⌁","Research"],["future","◇","Future relevance research"],["logistics","▧","Cognitive logistics"],["connections","⇄","Connections"]];
let notificationTimer;
function localDay(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}
function contentNodes(children){return children.flat(Infinity).filter(c=>c!==null&&c!==undefined&&c!==false).map(c=>c instanceof Node?c:document.createTextNode(String(c)));}
function skipToMain(event){event.preventDefault();main.focus();}
function el(tag, attrs={}, ...children){const n=document.createElement(tag);for(const [key,val] of Object.entries(attrs)){if(key==="class")n.className=val;else if(key==="style")n.style.cssText=val;else if(key==="on")for(const [evt,fn] of Object.entries(val))n.addEventListener(evt,fn);else if(key==="text")n.textContent=val;else if(val!==null&&val!==undefined&&val!==false)n.setAttribute(key,val===true?"":String(val));}n.append(...contentNodes(children));return n;}
function button(label,fn,cls="secondary",attrs={}){return el("button",{type:"button",class:cls,on:{click:fn},...attrs},label);}
function badge(text,kind=""){return el("span",{class:`badge ${kind}`},text);}
function heading(title,subtitle,actions=[]){return el("div",{class:"page-heading"},el("div",{},el("p",{class:"eyebrow"},"YOUR FOOTBALL WORKSPACE"),el("h1",{},title),el("p",{},subtitle)),el("div",{class:"heading-actions"},actions));}
function panel(title,...content){return el("section",{class:"panel"},title?el("h2",{},title):null,...content);}
function note(text){return el("p",{class:"note"},text);}
function notify(text){const n=document.querySelector("#notification");n.textContent=text;n.hidden=false;clearTimeout(notificationTimer);notificationTimer=setTimeout(()=>n.hidden=true,7000);}
function humanDate(s){if(!s)return "Date unavailable";const p=String(s).split("T")[0].split("-").map(Number);if(p.length!==3||p.some(x=>!Number.isFinite(x)))return String(s);return new Intl.DateTimeFormat(undefined,{day:"numeric",month:"short",year:"numeric"}).format(new Date(p[0],p[1]-1,p[2],12));}
function time(s){if(!s)return "Not supplied";const d=new Date(s);return Number.isNaN(d.valueOf())?String(s):new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(d);}
function safeUrl(value){try{const u=new URL(value,location.origin);return ["http:","https:"].includes(u.protocol)?u.href:null;}catch{return null;}}
function link(label,url,attrs={}){const safe=safeUrl(url);return safe?el("a",{href:safe,target:"_blank",rel:"noopener noreferrer",...attrs},label):el("span",{},label);}
async function request(path,opts={}){const ctrl=new AbortController();const logisticsTraining=path==="/logistics/training";const timeoutMs=logisticsTraining?600000:path==="/future/training"?300000:20000;const timer=setTimeout(()=>ctrl.abort(),timeoutMs);try{const headers={Accept:"application/json",...opts.headers};if(opts.body)headers["Content-Type"]="application/json";const response=await fetch(API+path,{credentials:"same-origin",...opts,headers,signal:ctrl.signal});const body=await response.json().catch(()=>({}));if(!response.ok){if(response.status===401){state.authenticated=false;showLogin();}const error=new Error(body.error?.message||body.detail?.message||body.detail||`Request failed (${response.status})`);error.status=response.status;error.code=body.error?.code;throw error;}return body;}catch(err){if(err.name==="AbortError")throw new Error(logisticsTraining?"The logistics training request reached its ten-minute waiting limit. Completion is uncertain; refresh retained experiment results before retrying. This request was not replayed.":path==="/future/training"?"Training request timed out. Refresh retained experiment results before submitting again.":"The server did not respond within 20 seconds. Retry when it is ready.");if(err instanceof TypeError)throw new Error(logisticsTraining?"The logistics training connection ended before confirmation. Completion is uncertain; refresh retained experiment results before retrying.":"The server is unreachable. Check the connection and retry; your retained data remains on the server.");throw err;}finally{clearTimeout(timer);}}
function errorView(err,retry=()=>render()){return panel("Unable to load this view",el("p",{class:"error-text",role:"alert"},err.message||String(err)),button("Retry",retry,"primary"),button("Open connections",()=>go("connections"),"secondary"));}
function go(route){state.scrolls.set(location.hash||"#today",window.scrollY);location.hash=route;}
function selectMatch(m){state.previous=location.hash||"#history";state.match=m;state.tab="overview";sessionStorage.setItem("dragonhydra.match",m.id);go(`match/${encodeURIComponent(m.id)}`);}
function back(){go(state.previous.replace(/^#/,"")||"history");}
function loading(label="Loading retained evidence…"){return el("div",{class:"loading",role:"status"},label);}
function empty(title,text,actions=[]){return el("section",{class:"panel empty"},el("div",{class:"empty-icon","aria-hidden":"true"},"◈"),el("h2",{},title),el("p",{},text),el("div",{class:"actions"},actions));}
function updateNav(route){for(const item of document.querySelectorAll("#navigation a")){const active=item.dataset.route===route;item.classList.toggle("active",active);active?item.setAttribute("aria-current","page"):item.removeAttribute("aria-current");}document.querySelector("#breadcrumb").textContent=route==="history"?"Retained matches":navItems.find(x=>x[0]===route)?.[2]||({match:"Match detail",team:"Team",standings:"Standings"}[route]||"Workspace");}
async function render(){const route=(location.hash.slice(1)||"today").split("/");if(route[0]==="token=")return;const version=++state.render;state.route=route[0];if(route[0]!=="research")window.DragonRealtime?.stop();if(route[0]!=="future")window.DragonFuture?.stop();if(route[0]!=="logistics")window.DragonLogistics?.stop();updateNav(route[0]);const scroll=state.scrolls.get(location.hash||"#today")||0;state.lastHash=location.hash||"#today";main.replaceChildren(loading());try{let content;if(["today","live","history"].includes(route[0]))content=await matchesView(route[0]);else if(route[0]==="match")content=await matchView(decodeURIComponent(route.slice(1).join("/")));else if(route[0]==="team")content=await teamView(decodeURIComponent(route.slice(1).join("/")));else if(route[0]==="standings")content=await standingsView(decodeURIComponent(route.slice(1).join("/")));else if(route[0]==="competitions")content=await competitionsView();else if(route[0]==="teams")content=await teamsView();else if(route[0]==="research")content=await window.DragonRealtime.view({request});else if(route[0]==="future")content=await window.DragonFuture.view({request});else if(route[0]==="logistics")content=await window.DragonLogistics.view({request});else if(route[0]==="connections")content=await connectionsView();else if(route[0]==="source")content=await sourceView(decodeURIComponent(route[1]));else if(["odds","analysis"].includes(route[0]))content=await selectedView(route[0]);else content=empty("Choose a view","Open Today to browse the schedule, or view retained public results.",[button("Open Today",()=>go("today"),"primary")]);if(version!==state.render)return;main.replaceChildren(...contentNodes([content]));window.scrollTo(0,scroll);sessionStorage.setItem("dragonhydra.route",location.hash);}catch(err){if(version===state.render)main.replaceChildren(errorView(err));}}
function matchCard(m){return el("button",{type:"button",class:"match-card","data-match-id":m.id,"aria-label":`Open match: ${m.home.name} versus ${m.away.name}`,on:{click:()=>selectMatch(m)}},el("time",{datetime:m.event_date},humanDate(m.event_date),el("small",{},m.kickoff_utc?time(m.kickoff_utc):"Time not supplied")),el("span",{class:"team-label"},m.home.name),el("span",{class:"score"},m.score?`${m.score.home} : ${m.score.away}`:"—"),el("span",{class:"team-label away"},m.away.name),el("span",{class:"match-state"},badge(m.status==="finished"?(m.source_id.startsWith("openfootball-")||m.source_id==="football-data-couk"?"FULL TIME":"RETAINED SCORE"):m.status.toUpperCase()),el("small",{},m.data_state||"Retained")));}
function importButton(){return button("Import retained public results",()=>startImport(),"primary",{"data-action":"import"});}
async function matchesView(mode){const isHistory=mode==="history",isLive=mode==="live";const q=new URLSearchParams({limit:state.limit,offset:state.offset});if(!isHistory&&!isLive)q.set("date",state.date);if(isLive)q.set("status","live");if(state.search)q.set("search",state.search);if(state.competition)q.set("competition",state.competition);const [data,competitions]=await Promise.all([request("/matches?"+q),request("/competitions")]);const title=isHistory?"Retained matches":isLive?"Live football":"Today’s football";const fragment=el("div",{},heading(title,isHistory?"Real source records, available whenever you need them.":isLive?"Active matches from supported, configured live sources.":"Choose a match. Follow the evidence.",[button(isHistory?"Today":"Browse retained matches",()=>{state.offset=0;go(isHistory?"today":"history");}),importButton()]));const search=el("input",{id:"match-search",type:"search",value:state.search,placeholder:"Search teams","aria-label":"Search matches"});const date=el("input",{id:"match-date",type:"date",value:state.date});const competition=el("select",{id:"match-competition"},el("option",{value:""},"All competitions"),(competitions.items||[]).map(c=>el("option",{value:c.id},c.name)));competition.value=state.competition;const toolbar=el("form",{class:"toolbar",on:{submit:ev=>{ev.preventDefault();state.search=search.value.trim();state.competition=competition.value;state.date=date.value||localDay();state.offset=0;render();}}},el("div",{class:"grow"},el("label",{for:"match-search"},"FIND A MATCH"),search),el("div",{},el("label",{for:"match-competition"},"COMPETITION"),competition),!isHistory&&!isLive?el("div",{},el("label",{for:"match-date"},"MATCH DATE"),date):null,el("button",{type:"submit",class:"secondary"},"Apply filters"));fragment.append(toolbar);if(!data.items?.length){fragment.append(empty(isLive?"No live matches available":isHistory?"Your match library starts here":"No retained matches for this date",isLive?"OpenFootball provides published fixtures and results, not a live stream. Set up a supported source in Connections or browse retained results.":isHistory?"Import a manageable set of public OpenFootball results. No account or model download is needed.":"The selected date has no records in your retained data. Browse historical matches or synchronize a public source.",[isHistory?importButton():button("Browse retained matches",()=>{state.offset=0;go("history");},"primary"),button("Connections",()=>go("connections"))]));}else{fragment.append(el("div",{class:"section-title"},el("h2",{},isHistory?"Match library":"Match schedule"),el("span",{class:"count"},`${data.total} match${data.total===1?"":"es"} · ${isLive?"Live source":"Retained evidence"}`)),el("div",{class:"match-list"},data.items.map(matchCard)));const actions=[];if(state.offset>0)actions.push(button("Previous",()=>{state.offset=Math.max(0,state.offset-state.limit);render();}));if(state.offset+state.limit<data.total)actions.push(button("Next",()=>{state.offset+=state.limit;render();}));fragment.append(el("div",{class:"pagination"},el("span",{},`${state.offset+1}–${Math.min(state.offset+state.limit,data.total)} of ${data.total}`),el("div",{class:"actions"},actions)));}return fragment;}
function sourceDetails(m){const values=[["Source",m.source_id],["Evidence ID",m.evidence_id],["Match ID",m.id],["Resource version",m.version],["Received",time(m.received_at)],["Usable after",time(m.usable_at)],["Kickoff UTC",m.kickoff_utc||"Not supplied; date-only source precision"]];return el("details",{class:"technical"},el("summary",{},"Technical details"),el("dl",{},values.flatMap(([k,v])=>[el("dt",{},k),el("dd",{},v??"Not supplied")])),link("Open original source",m.source_url));}
function hero(m){return el("section",{class:"panel match-hero"},el("div",{class:"match-meta"},el("span",{},`${m.competition} · ${m.season||"Source season"}`),badge(m.data_state||"Retained","amber"),el("span",{},humanDate(m.event_date))),el("div",{class:"match-scoreboard"},teamButton(m.home),el("div",{class:"hero-score"},m.score?`${m.score.home} : ${m.score.away}`:"—",el("small",{},m.status==="finished"?(m.source_id.startsWith("openfootball-")||m.source_id==="football-data-couk"?"FULL TIME":"RETAINED SCORE"):m.status.toUpperCase())),teamButton(m.away)),el("div",{class:"source-line"},`Source: ${m.source_id} · Imported ${time(m.received_at)} · ${m.kickoff_utc?"Kickoff shown in your timezone":"UTC kickoff / source timezone unverified"}`));}
function teamButton(t){return button([el("span",{class:"team-crest","aria-hidden":"true"},t.name.split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join("")),t.name],()=>go(`team/${encodeURIComponent(t.id)}`),"team-button",{"data-team-id":t.id,"aria-label":`View team ${t.name}`});}
async function matchView(id){const m=await request(`/matches/${encodeURIComponent(id)}`);state.match=m;sessionStorage.setItem("dragonhydra.match",m.id);const body=el("div",{},button("← Back to matches",back,"back"),hero(m));const tabs=el("div",{class:"tabs",role:"tablist","aria-label":"Match information"});const content=el("div",{id:"match-content"});const tabDefs=[["overview","Overview"],["odds","Odds & chart"],["analysis","Analysis"],["lineups","Lineups"],["statistics","Statistics"]];for(const [key,label]of tabDefs){tabs.append(button(label,async()=>{state.tab=key;for(const t of tabs.children){t.classList.toggle("active",t.dataset.tab===key);t.setAttribute("aria-selected",String(t.dataset.tab===key));}await loadTab(content,m,key);},`tab ${state.tab===key?"active":""}`,{role:"tab","aria-selected":String(state.tab===key),"data-tab":key}));}body.append(tabs,content);await loadTab(content,m,state.tab);return body;}
async function loadTab(content,m,tab){content.replaceChildren(loading());try{if(tab==="overview"){content.replaceChildren(el("div",{class:"two-columns"},panel("Match overview",el("div",{class:"fact-grid"},fact("Competition",m.competition),fact("Season",m.season||"Not supplied"),fact("State",m.status==="finished"?"Finished":"Scheduled"),fact("Match date",humanDate(m.event_date))),el("div",{class:"actions",style:"margin-top:22px"},button("Open standings",()=>go(`standings/${encodeURIComponent(m.competition_id)}`),"primary"),button("Export to Excel",()=>startExport(m,"xlsx"),"secondary",{"data-action":"export"})),sourceDetails(m)),panel("What the source tells us",el("ul",{class:"facts-list"},el("li",{},m.score?"The full-time score is a retained source observation.":"The source does not yet supply a final score."),el("li",{},"Lineups, injuries and player statistics are shown only when supplied by a configured source."),el("li",{},"Historical results are available after import; they do not establish what was known before kickoff.")),button("View model probabilities",()=>{state.tab="analysis";render();},"inline-link"))));}else if(tab==="odds")content.replaceChildren(await oddsPanel(m));else if(tab==="analysis")content.replaceChildren(await analysisPanel(m));else{const context=await sourceContextPanel(m,tab);if(context){content.replaceChildren(context);return;}const data=await request(`/matches/${encodeURIComponent(m.id)}/${tab}`);content.replaceChildren(panel(tab==="lineups"?"Lineups":"Match statistics",data.items?.length?table(["Statistic","Source value"],data.items.map(x=>[String(x.statistic||"Source context").replaceAll("_"," "),typeof x.value==="object"?JSON.stringify(x.value):x.value])):el("p",{class:"muted"},data.reason||"This source does not supply this information. Missing data does not indicate a healthy or complete squad."),button("Check source capabilities",()=>go("connections"))));}}catch(err){content.replaceChildren(errorView(err,()=>loadTab(content,m,tab)));}}
async function sourceContextPanel(m,tab){
  if(m.source_id!=="statsbomb")return null;
  let data;
  try{data=await request(`/matches/${encodeURIComponent(m.id)}/source-context`);}
  catch(error){if(error.status===404)return null;throw error;}
  if(!data.supported)return null;
  const available=data.availability==="available"&&data.projection;
  const reasons={available:"Retained public event records and team sheet entries for this match.",
    not_requested:"Load public event records and team sheet entries for this match.",
    parent_changed:"The match metadata changed after this context was retained. Load context for the updated match.",
    unavailable:"The retained source context could not be verified. The match record remains available."};
  const result=panel(tab==="lineups"?"StatsBomb source squad entries":"StatsBomb event records",
    el("p",{class:"muted"},reasons[data.availability]||data.reason));
  result.dataset.contextState=data.availability;
  result.append(badge(available?"RETAINED SOURCE CONTEXT":String(data.availability||"unavailable").replaceAll("_"," ").toUpperCase(),available?"green":"amber"));
  const load=button(available?"Refresh source context":"Load events and squads",async()=>{
    load.disabled=true;
    try{await runJob(`/matches/${encodeURIComponent(m.id)}/source-context`,{},async()=>{
      notify("StatsBomb source context is ready.");
      if(state.route==="match"&&state.match?.id===m.id)await render();
    });}finally{load.disabled=false;}
  },"secondary",{"data-action":"load-source-context"});
  result.append(el("div",{class:"actions",style:"margin-top:16px"},load),
    el("p",{class:"muted"},"This action downloads two public files, up to 8 MiB each. Viewing retained context sends no provider request."));
  if(available){
    const projection=data.projection,summary=projection.event_summary;
    result.append(el("p",{},`${summary.row_count} retained event records`),note("Counts describe retained source records, not official match statistics. Missing team or period values are shown as Not supplied."));
    if(tab==="lineups"){
      result.append(el("div",{class:"source-squads",style:"display:grid;gap:20px"},projection.squads.map(team=>
        el("section",{"data-source-team-id":team.team_id,style:"min-width:0"},el("h3",{},team.team_name),
          table(["Source player ID","Player","Nickname","Shirt number","Country"],team.lineup.map(player=>[
            player.player_id,player.player_name,player.player_nickname??"Not supplied",
            player.jersey_number??"Not supplied",player.country?.name??"Not supplied"]))))));
    }else{
      const teams=new Map(projection.squads.map(team=>[team.team_id,team.team_name]));
      const types=new Map(summary.types.map(type=>[type.id,type.name]));
      result.append(table(["Source team","Source period","Event type","Retained rows"],summary.counts_by_team_period_type.map(group=>[
        group.team_id===null?"Not supplied":teams.get(group.team_id)||String(group.team_id),
        group.period??"Not supplied",types.get(group.type_id)||String(group.type_id),group.count])));
      const pages=el("div",{"data-source-events":""});
      const showPage=async offset=>{
        pages.replaceChildren(loading("Reading retained event records…"));
        try{
          const page=await request(`/matches/${encodeURIComponent(m.id)}/source-events?offset=${offset}&limit=50`);
          if(page.availability!=="available"){
            pages.replaceChildren(note(page.reason||"Source event records are currently unavailable."));return;
          }
          pages.replaceChildren(el("h3",{},"Native event records"),table(
            ["Native index","Period","Timestamp","Minute","Second","Source team","Source player","Event type"],
            page.items.map(event=>[event.index,event.period??"Not supplied",event.timestamp??"Not supplied",
              event.minute??"Not supplied",event.second??"Not supplied",event.team?.name??"Not supplied",
              event.player?.name??"Not supplied",event.type.name])),
            el("div",{class:"pagination"},el("span",{},page.total===0?"No retained event rows":`${page.offset+1}–${page.offset+page.items.length} of ${page.total} source records`),
              el("div",{class:"actions"},page.offset>0?button("Previous events",()=>showPage(Math.max(0,page.offset-page.limit))):null,
                page.offset+page.limit<page.total?button("Next events",()=>showPage(page.offset+page.limit)):null)));
        }catch(error){pages.replaceChildren(errorView(error,()=>showPage(offset)));}
      };
      result.append(el("div",{class:"actions"},button("Browse retained event records",()=>showPage(0),"secondary",{"data-action":"browse-source-events"})),pages);
    }
  }
  result.append(el("p",{class:"muted"},data.attribution||"StatsBomb Open Data"));
  if(data.documents?.length)result.append(el("details",{class:"technical"},el("summary",{},"Context source receipts"),
    el("dl",{},data.documents.flatMap(document=>[el("dt",{},document.role),el("dd",{},
      link("Original source",document.original_url),` · Captured ${time(document.captured_at)} · SHA256 ${document.sha256}`)])),
    el("p",{},`Context ID: ${data.context_record_id||"Not retained"}`)));
  return result;
}
function fact(k,v){return el("div",{},el("div",{class:"fact-label"},k),el("div",{class:"fact-value"},v));}
async function oddsPanel(m){const [odds,historyData]=await Promise.all([request(`/matches/${encodeURIComponent(m.id)}/odds`),request(`/matches/${encodeURIComponent(m.id)}/odds-history`)]);return panel("Compatible odds & history",el("p",{class:"muted"},`${m.home.name} vs ${m.away.name} · ${humanDate(m.event_date)}`),!odds.items?.length?note(odds.reason||"No verified compatible market is mapped to this canonical match. Connect a provider or inspect another retained match."):table(["Provider","Market","Selection","Decimal odds"],odds.items.map(x=>[x.provider||x.provider_id,x.market||x.market_type,x.selection,x.decimal_odds||x.price])),el("h3",{},"Odds history"),historyData.items?.length?note(historyData.reason||"Retained observations are shown below; values are not interpolated."):el("p",{class:"muted"},historyData.reason||"No timed observations are available. A curve cannot be inferred from untimestamped archive prices."),historyData.items?.length?table([historyData.axis||"Capture time","Selection","Decimal odds"],historyData.items.map(x=>[historyData.axis==="archive_phase"?(x.archive_phase||"Archive endpoint"):time(x.captured_at||x.received_at),x.selection,x.decimal_odds||x.price])):null,button("Open connections",()=>go("connections")));}
async function analysisPanel(m){const p=await request(`/matches/${encodeURIComponent(m.id)}/predictions`);const result=panel("Model probabilities",el("p",{class:"muted"},`${m.home.name} vs ${m.away.name} · Same canonical event`));if(p.available&&p.ensemble){result.append(badge("STATISTICAL FORECAST","green"),el("div",{class:"probability-chart",role:"img","aria-label":"Outcome probabilities: home, draw and away"},["home","draw","away"].map((k,i)=>{const raw=typeof p.ensemble[k]==="object"?p.ensemble[k]?.value:p.ensemble[k];const value=Number(raw);return el("div",{class:"probability-row",title:`${k}: ${(value*100).toFixed(2)}%`},el("span",{},["Home win","Draw","Away win"][i]),el("div",{class:"bar-track"},el("div",{class:"bar-fill",style:`width:${Number.isFinite(value)?Math.min(100,Math.max(0,value*100)):0}%`})),el("strong",{},Number.isFinite(value)?`${(value*100).toFixed(1)}%`:"Unavailable"));})),el("p",{class:"muted"},p.interpretation||"Pre-match statistical estimates. They are not a live-state model."));if(p.expected_goals)result.append(el("p",{class:"muted"},`Expected goals: ${JSON.stringify(p.expected_goals)}`));}else result.append(note(p.reason||"No eligible pre-match forecast is available for this event. Historical data cannot establish a forecast made before the match."));if(p.cutoff)result.append(el("p",{class:"technical"},`Evidence cutoff: ${time(p.cutoff)}`));const explanation=panel("Investigate the evidence",el("p",{class:"muted"},"Explain this match creates a deterministic evidence summary. The optional local model selects one supplied source fact; it adds no new analysis or prediction. If the model is unavailable, the summary stays deterministic."),el("div",{class:"actions"},button("Explain this match",()=>startExplanation(m),"primary",{"data-action":"explain"}),button("Use local model",()=>startExplanation(m,true),"secondary",{"data-action":"local-explain"}),button("Configure local model",configureLocalModel,"secondary",{"data-action":"configure-local-model"}),button("Export sports package",()=>exportSportsPackage(m),"secondary",{"data-action":"export-sports-package"})),el("p",{class:"muted"},"The sports package contains this match’s retained facts, source citation and integrity hash. Local model setup belongs to this server."),el("div",{id:"local-model-settings"}),el("div",{id:"explanation-result"}));const contextControls=await contextAnalysisControls(m);if(contextControls)explanation.append(contextControls);return el("div",{},result,explanation);}
async function selectedView(mode){const id=state.match?.id||sessionStorage.getItem("dragonhydra.match");if(!id)return [heading(mode==="odds"?"Odds":"Analysis","Your selected match stays with you."),empty("Choose a match first","Open a retained match to inspect compatible odds, model probabilities and evidence-linked explanations.",[button("Browse retained matches",()=>go("history"),"primary")])];const m=state.match?.id===id?state.match:await request(`/matches/${encodeURIComponent(id)}`);state.match=m;return [heading(mode==="odds"?"Odds":"Analysis",`${m.home.name} vs ${m.away.name}`,[button("Open selected match",()=>go(`match/${encodeURIComponent(id)}`))]),mode==="odds"?await oddsPanel(m):await analysisPanel(m)];}
async function teamsView(){const data=await request("/teams");const teams=(data.items||[]).sort((a,b)=>a.name.localeCompare(b.name));return [heading("Teams","Explore the teams in your retained fixtures."),teams.length?panel("Team directory",el("div",{class:"list-links"},teams.map(t=>button([el("span",{},t.name,el("small",{class:"muted"},t.competition?` · ${t.competition}`:"")),el("span",{class:"muted","aria-hidden":"true"},"→")],()=>go(`team/${encodeURIComponent(t.id)}`))))):empty("No teams imported yet","Import public results to build your team directory.",[importButton()])];}
async function teamView(id){const t=await request(`/teams/${encodeURIComponent(id)}`);const form=(t.form||[]).slice(0,10);return [button("← Return to selected match",()=>state.match?go(`match/${encodeURIComponent(state.match.id)}`):back(),"back"),heading(t.name,"Recent form and fixtures from retained observations."),panel("Recent form",form.length?el("div",{class:"form-strip"},form.map(x=>button(x.result||"?",()=>go(`match/${encodeURIComponent(x.match_id)}`),`form-token ${x.result==="W"?"win":x.result==="D"?"draw":""}`,{title:`${humanDate(x.date)} · ${x.opponent} · ${x.goals_for}–${x.goals_against}`,"aria-label":`${x.result}: ${x.opponent}, ${x.goals_for} to ${x.goals_against}, ${humanDate(x.date)}`}))):el("p",{class:"muted"},"No retained completed results for this team."),note((t.unknowns||[]).join(" ")||"Squads, injuries and suspensions are not supplied by this public results source. Missing injury data does not mean a fully healthy squad.")),el("div",{class:"section-title"},el("h2",{},"Retained matches"),el("span",{class:"count"},`${t.matches?.length||0} fixtures`)),el("div",{class:"match-list"},(t.matches||[]).map(matchCard))];}
async function competitionsView(){const data=await request("/competitions");return [heading("Competitions","Standings retain their source, season and limitations."),data.items?.length?panel("Your competitions",el("div",{class:"list-links"},data.items.map(c=>button([el("span",{},c.name,el("small",{class:"muted"},` · ${c.season||"Source season"}`)),el("span",{"aria-hidden":"true"},"→")],()=>go(`standings/${encodeURIComponent(c.id)}`))))):empty("No competitions imported yet","Import public fixtures to view competition context.",[importButton()])];}
function table(headers,rows){return el("div",{class:"table-wrap"},el("table",{},el("thead",{},el("tr",{},headers.map(h=>el("th",{scope:"col"},h)))),el("tbody",{},rows.map(cells=>el("tr",{},cells.map(c=>el("td",{},c??"—")))))));}
async function standingsView(id){const s=await request(`/competitions/${encodeURIComponent(id)}/standings`);return [button("← Return to selected match",()=>state.match?go(`match/${encodeURIComponent(state.match.id)}`):go("competitions"),"back"),heading(s.competition,`${s.season||"Source season"} · ${s.label||"Reconstructed from retained results"}`,[badge(s.available===false?"UNAVAILABLE":s.official?"OFFICIAL SOURCE":"RECONSTRUCTED","amber")]),note(s.available===false?s.label:s.official?"Supplied provider standings.":"Reconstructed from retained results using three points for a win. Official deductions and tie-break rules may be unavailable."),s.stages?note("Retained stages: "+s.stages.join(", ")):null,s.items?.length?table(["Team","P","W","D","L","GF","GA","Pts"],s.items.map(x=>[button(x.team,()=>go(`team/${encodeURIComponent(x.team_id)}`),"inline-link"),x.played,x.won,x.drawn,x.lost,x.goals_for,x.goals_against,el("strong",{},x.points)])):empty(s.available===false?"Standings are unavailable for this source scope":"No completed results available",s.available===false?(s.label||s.reason||"The retained records do not support a single table. Read the scope limitations below."):"Standings require retained results for this competition."),el("p",{class:"technical"},`Source: ${s.source_id||"Retained results"} · Calculated/read at ${time(s.as_of)}. This does not refresh retained source timestamps.`),(s.limitations||[]).map(note)];}
async function connectionsView(){
  const data=await request('/connections');
  const labels={working:'Working',failing:'Failing',needs_key:'Needs key',not_tested:'Test required',checking:'Checking'};
  return [heading('Connections','Test a source → synchronize → open retained data. Public downloads need no account.'),
    note('Historical downloads are not live feeds. Each source retains its own identities and exact source evidence.'),
    el('div',{class:'connection-grid'},data.items.map(c=>{
      const proof=el('div',{class:'connection-proof',role:'status'});
      const actions=[];
      if(c.id==='openfootball') actions.push(importButton(),button('Test connection',async()=>{
        try{const r=await request('/connections/openfootball/test',{method:'POST',body:'{}'});proof.textContent=`${r.status}: ${r.record_count||0} retrieved rows. ${r.reason||''}`;}catch(e){proof.textContent=e.message;}
      },'secondary small'));
      else if(c.implemented){
        const perform=async action=>{
          await runJob(`/connections/${encodeURIComponent(c.id)}/${action}`,{},async r=>{
            notify(`${c.name}: ${r.status}; ${r.retrieved_rows||0} retrieved, ${r.normalized_rows||0} valid, ${r.record_count||0} stored.`);
            if(location.hash==='#connections') await render();
          });
          if(location.hash==='#connections'){
            const latest=(await request('/connections')).items.find(x=>x.id===c.id);
            const card=document.querySelector(`[data-provider="${c.id}"]`);
            if(card&&latest?.last_diagnostic?.error){
              const target=card.querySelector('.connection-proof');
              target.textContent=`${latest.last_diagnostic.error.code}: ${latest.reason}`;
              card.querySelector('.badge').textContent=labels[latest.status]||latest.status;
            }
          }
        };
        actions.push(button('Test connection',()=>perform('test'),'secondary small'),button('Sync now',()=>perform('sync'),'primary small'));
        if(c.record_count)actions.push(button('Open imported data',()=>go(`source/${c.id}`),'secondary small'));
      }
      if(c.registration_url)actions.push(link(c.requires_key?'Register / get API key ↗':'Source documentation ↗',c.registration_url,{class:'small'}));
      const card=el('section',{class:'panel connection-card','data-provider':c.id},
        el('div',{class:'connection-title'},el('h2',{},c.name),badge(labels[c.status]||c.status,c.status==='working'||c.record_count&&c.id==='openfootball'?'green':c.status==='failing'?'amber':'')),
        el('p',{},c.reason),el('div',{class:'tag-list'},c.capabilities.map(x=>el('span',{},x))),
        el('p',{},`${c.record_count||0} stored records · Last import: ${time(c.last_import)}`),
        el('p',{class:'muted'},`Last successful retrieval: ${time(c.last_successful_retrieval||c.last_import)} · ${c.last_retrieval_count??c.record_count??0} rows`),
        c.quarantined_count?note(`${c.quarantined_count} invalid or ambiguous observations quarantined; no silent identity joins.`):null,
        el('div',{class:'actions'},actions),proof);
      if(c.id!=='openfootball'&&c.implemented){
        const interval=el('select',{'aria-label':`${c.name} refresh interval`});
        const minimum=c.minimum_interval_seconds||3600;
        const choices=[0,...new Set([minimum,Math.min(minimum*6,604800),86400].filter(x=>x>=minimum))];
        for(const seconds of choices)interval.append(el('option',{value:seconds},seconds?`Every ${seconds/3600>=1?`${seconds/3600} hours`:`${seconds/60} minutes`}`:'Manual only'));
        interval.value=String(c.interval_seconds||0);
        const credential=el('input',{type:'password',autocomplete:'new-password','aria-label':`${c.name} API key`,placeholder:c.credential_configured?'Key saved securely; enter to replace':'Provider API key'});
        const config=el('textarea',{'aria-label':`${c.name} dataset settings`,rows:5},JSON.stringify(c.config||{},null,2));
        const save=button('Save connection',async()=>{
          try{
            const payload={config:JSON.parse(config.value),interval_seconds:Number(interval.value)};
            if(credential.value)payload.credential=credential.value;
            await request(`/connections/${c.id}/configuration`,{method:'PUT',body:JSON.stringify(payload)});
            credential.value='';notify('Connection saved. Test retrieval to verify coverage.');await render();
          }catch(e){proof.textContent=e.message;}
        },'secondary small');
        card.append(el('details',{},el('summary',{},'Configure connection'),
          c.requires_key?el('label',{},'API key (encrypted for the server service account)',credential):null,
          el('label',{},'Automatic refresh',interval),note('Refresh jobs run once on the server, shared by all clients. Provider quota limits still apply.'),
          el('details',{},el('summary',{},'Dataset settings'),config),save,
          c.requires_key?note('Keys stay on the server. Changing the Windows service identity requires reauthorization; keys are not included in exports.'):null));
      }
      return card;
    })),panel('Administration',note('Source settings and keys are protected by server-side administrator permissions.'),button('Administration',openAdministration))];
}

async function sourceView(id){
  const filter=state.sourceFilter||'';
  const data=await request(`/connections/${encodeURIComponent(id)}/records?limit=100&offset=${state.sourceOffset||0}${filter?`&status=${encodeURIComponent(filter)}`:''}`);
  const providers=await request('/connections');const provider=providers.items.find(x=>x.id===id);
  const select=el('select',{'aria-label':'Record type',on:{change:ev=>{state.sourceFilter=ev.target.value;state.sourceOffset=0;render();}}});
  for(const value of ['', 'historical_result','scheduled','live','cancelled','synthetic'])select.append(el('option',{value},value||'All retained record types'));
  select.value=filter;
  return [button('← Connections',()=>go('connections'),'back'),heading(provider?.name||id,`${data.total} retained source records. Participants and evidence remain source-scoped.`),
    el('label',{},'Filter record type',select),note(data.identity_policy),
    table(['Date','Sport / competition','Participants','Record type','Result','Evidence'],data.items.map(item=>{
      const r=item.record;const title=`${r.home} vs ${r.away}`;
      const result=r.score_home!==null&&r.score_home!==undefined&&r.score_away!==null&&r.score_away!==undefined?`${r.score_home}–${r.score_away}`:'See source statistics';
      return [humanDate(r.event_date),`${r.sport} · ${r.competition} ${r.season||''}`,item.match_id?button(title,()=>go(`match/${item.match_id}`),'inline-link'):title,r.status,result,
        link('Source record',item.evidence_url,{target:'_blank',rel:'noopener'})];
    })),el('div',{class:'actions'},button('Previous records',()=>{state.sourceOffset=Math.max(0,(state.sourceOffset||0)-100);render();},'secondary',{disabled:!(state.sourceOffset||0)}),
      button('Next records',()=>{state.sourceOffset=(state.sourceOffset||0)+100;render();},'secondary',{disabled:(state.sourceOffset||0)+100>=data.total})),
    note('Exact downloaded bytes, source identifiers, adapter version and UTC receipt times are linked from each evidence record. Cricket participant order does not imply home advantage.')];
}
async function startImport(){await runJob("/connections/openfootball/sync",{},async result=>{notify(`Import complete: ${result?.inserted??0} new records; ${result?.record_count??"public"} retained matches. Open your match library.`);state.offset=0;state.search="";state.competition="";if(location.hash==="#history")render();else go("history");});}
async function startExport(m,format){await runJob("/exports",{match_id:m.id,format},result=>{const n=el("div",{class:"export-result"},el("strong",{},"Report ready"),el("p",{},result.filename||"Your report"),el("p",{},"Choose Download. Your browser saves the workbook to its configured downloads folder."),link("Download Excel report",result.download_url,{target:"_self",download:result.filename||"dragonhydra-report.xlsx"}));main.append(n);n.scrollIntoView({behavior:"smooth",block:"nearest"});notify("Your report is ready to download.");});}
async function configureLocalModel(){
  const container=document.querySelector('#local-model-settings');
  if(!container)return;
  container.replaceChildren(note('Loading local model settings…'));
  try{
    let current=await request('/local-model/configuration');
    const endpoint=el('input',{type:'url',value:current.endpoint||'',id:'local-model-endpoint','aria-label':'Local model endpoint',autocomplete:'off',placeholder:'Configure an optional local model endpoint'});
    const key=el('input',{type:'password',id:'local-model-key','aria-label':'Local model API key',autocomplete:'new-password',maxlength:4096,placeholder:current.credential_source!=='none'?'Key available; enter to replace saved key':'Model server API key'});
    const status=el('p',{role:'status',class:'local-model-status'});
    const showStatus=()=>{status.textContent=`${current.configured?'Endpoint and key configured':'Endpoint or key still needed'} · Endpoint: ${current.endpoint_source==='environment'?'service environment':current.endpoint_source==='stored'?'saved on server':'not set'} · Key: ${current.credential_source==='environment'?'service environment':current.credential_source==='vault'?'saved securely':'not set'}. Configuration does not prove the model is running.`;};
    const save=button('Save local model',()=>persist(false),'secondary small');
    const remove=button('Remove saved model key',()=>persist(true),'secondary small');
    const persist=async removing=>{
      save.disabled=true;remove.disabled=true;
      try{
        const payload={endpoint:endpoint.value,remove_credential:removing};
        if(!removing&&key.value)payload.credential=key.value;
        current=await request('/local-model/configuration',{method:'PUT',body:JSON.stringify(payload)});
        showStatus();
        notify(removing?(current.credential_source==='environment'?'Saved key removed. The service environment key is still active.':'Saved model key removed.'):'Local model settings saved. Use local model to request a source fact.');
      }catch(error){status.textContent=error.message;}
      finally{key.value='';save.disabled=false;remove.disabled=false;}
    };
    showStatus();
    container.replaceChildren(el('h3',{},'Configure local model'),el('label',{for:'local-model-endpoint'},'Model endpoint on this server',endpoint),el('label',{for:'local-model-key'},'Model API key',key),status,el('div',{class:'actions'},save,remove),note('Saved keys belong to this Windows server account. Service environment settings take precedence. Saving does not start or download a model.'));
    endpoint.focus();
  }catch(error){container.replaceChildren(note(error.message));}
}
async function contextAnalysisControls(m){
  if(m.source_id!=="statsbomb")return null;
  let data;
  try{data=await request(`/matches/${encodeURIComponent(m.id)}/source-context`);}
  catch(error){if(error.status===404)return null;return note("Source row counts could not be checked. The existing explanation actions remain available.");}
  if(!data.supported)return null;
  const controls=el("div",{"data-context-ai":""},el("h3",{},"Optional source row counts"));
  const available=data.availability==="available"&&data.projection&&
    /^source_context:[a-f0-9]{64}$/.test(data.context_record_id||"")&&data.context_parent_observation_id===m.evidence_id;
  if(!available){
    const reasons={not_requested:"Load events and squads in Statistics to add source row counts.",
      parent_changed:"The match metadata changed. Refresh its source context in Statistics before adding row counts.",
      unavailable:"Retained source row counts could not be verified. The existing explanation actions remain available."};
    controls.append(el("p",{class:"muted"},reasons[data.availability]||"Refresh this match and its source context before adding row counts."),
      button("Open retained source context",()=>{state.tab="statistics";const route=`match/${encodeURIComponent(m.id)}`;if(location.hash==="#"+route)render();else go(route);},"secondary small"));
    return controls;
  }
  const summary=data.projection.event_summary;
  controls.append(el("p",{},`${summary.row_count} retained event rows · ${data.projection.squads.map(team=>`${team.team_name}: ${team.lineup.length} squad entries`).join(" · ")}`),
    el("p",{class:"muted"},"Add these three source counts to an optional model request or package. Counts describe retained rows, not official match statistics or starting teams. These actions use retained documents."));
  let requestKey=null;
  const use=button("Use local model with source counts",async()=>{
    if(!requestKey)requestKey=crypto.randomUUID();
    use.disabled=true;
    try{if(await startExplanation(m,true,data.context_record_id,requestKey))requestKey=null;}
    finally{use.disabled=false;}
  },"secondary",{"data-action":"local-explain-context"});
  controls.append(el("div",{class:"actions"},use,
    button("Export package with source counts",()=>exportSportsPackage(m,data.context_record_id),"secondary",{"data-action":"export-context-package"})));
  return controls;
}
async function exportSportsPackage(m,contextRecordId=null){
  try{
    const query=contextRecordId?`?context_record_id=${encodeURIComponent(contextRecordId)}`:"";
    const packageData=await request(`/matches/${encodeURIComponent(m.id)}/analysis-package${query}`);
    const url=URL.createObjectURL(new Blob([JSON.stringify(packageData,null,2)+"\n"],{type:"application/json"}));
    const download=el("a",{href:url,download:`dragonhydra-sports-${contextRecordId?"context-":""}${m.id.slice(0,12)}.json`});
    document.body.append(download);download.click();download.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    notify("Sports package ready. Your browser saves the JSON to its downloads folder.");
  }catch(err){notify(err.message);}
}
async function startExplanation(m,useLocal=false,contextRecordId=null,requestKey=null){
  const endpoint=useLocal?"local-explanations":"explanations";
  const payload=useLocal&&contextRecordId?{context_record_id:contextRecordId}:{};
  return runJob(`/matches/${encodeURIComponent(m.id)}/${endpoint}`,payload,result=>{
    let target=document.querySelector("#explanation-result");
    if(!target){target=el("div",{id:"explanation-result"});main.append(target);}
    const accepted=result.kind==="local_llm"&&result.mode==="constrained_source_fact_selection";
    const rows=[badge(accepted?"LOCAL MODEL · SOURCE FACT SELECTION":"DETERMINISTIC EVIDENCE SUMMARY",accepted?"green":"amber")];
    if(useLocal&&!accepted&&result.local_ai){
      const diagnostic=result.local_ai;
      rows.push(el("p",{class:"note local-ai-diagnostic",role:"status"},`${diagnostic.code||"AI_UNAVAILABLE"}: ${diagnostic.message||"The local model is unavailable."} Check the offline model setup on this server, then retry Use local model.`));
    }
    rows.push(el("p",{},result.summary||"Evidence summary"),el("ul",{class:"facts-list"},(result.observations||[]).map(x=>el("li",{},typeof x==="string"?x:JSON.stringify(x)))),...(result.unknowns||[]).map(note),el("h3",{},"Cited evidence"),...(result.evidence||[]).map(x=>link(x.label||x.id,x.url,{class:"explanation-citation"})));
    target.replaceChildren(...rows);target.scrollIntoView({behavior:"smooth",block:"nearest"});
  },requestKey?{"Idempotency-Key":requestKey}:{});
}
async function runJob(path,payload,onSuccess,headers={}){if(state.activeJob){notify("A job is already running. Follow its progress or cancel it first.");return false;}state.activeJob="submitting";let box=el("section",{class:"job-progress",role:"status"},el("strong",{},"Submitting job…"));main.prepend(box);let terminal=false;try{const job=await request(path,{method:"POST",body:JSON.stringify(payload),headers});state.activeJob=job.id;const deadline=Date.now()+120000;let cancelled=false;for(;;){const j=await request(`/jobs/${encodeURIComponent(job.id)}`);const progress=Number(j.progress);box.replaceChildren(el("strong",{},`Job ${j.status}`),el("p",{},j.message||j.error?.message||"The worker is processing retained data. You can continue browsing."),el("progress",{max:100,value:Number.isFinite(progress)?Math.min(100,Math.max(0,progress<=1?progress*100:progress)):0}),el("div",{class:"actions"},button("Cancel job",async()=>{if(cancelled)return;cancelled=true;try{await request(`/jobs/${encodeURIComponent(job.id)}/cancel`,{method:"POST",body:"{}"});notify("Cancellation requested.");}catch(err){notify(err.message);}},"secondary small")));if(j.status==="succeeded"){box.remove();state.activeJob=null;await onSuccess(j.result||{});return true;}if(["failed","cancelled","interrupted"].includes(j.status)){terminal=true;throw new Error(j.error?.message||j.error||`Job ${j.status}. Retry from the original action when ready.`);}if(Date.now()>deadline)throw new Error(`The job is still ${j.status}. It remains on the server; retry this view to check progress.`);await new Promise(r=>setTimeout(r,550));}}catch(err){box.replaceChildren(el("strong",{},"Job needs attention"),el("p",{class:"error-text",role:"alert"},err.message),button("Dismiss",()=>box.remove(),"secondary small"));}finally{state.activeJob=null;}return terminal?"terminal":false;}
async function openAdministration(){try{const info=await request("/system");if(info.administration_url){const url=safeUrl(info.administration_url);if(url)window.open(url,"_blank","noopener,noreferrer");}else notify("Administration is not configured in this development checkpoint. The Joomla extension must be installed into a product-owned instance first.");}catch(err){notify(err.message);}}
function showLogin(){const dialog=document.querySelector("#login-dialog");if(!dialog.open)dialog.showModal();}
async function coreNextIdentity(){const live=await request("/health/live");const identity=live.installation;if(live.product!=="DRAGONHYDRA CORE NEXT"||identity?.edition!=="CORE NEXT"||typeof identity.installation_id!=="string")throw new Error("This address is not a CORE NEXT backend. No pairing credentials were sent.");const expected=sessionStorage.getItem("core-next.installation-id");if(expected&&expected!==identity.installation_id)throw new Error("This address belongs to a different CORE NEXT installation. Open its own launcher before pairing.");sessionStorage.setItem("core-next.installation-id",identity.installation_id);return identity;}
async function login(token){await coreNextIdentity();await request("/session",{method:"POST",body:JSON.stringify({token})});document.querySelector("#login-dialog").close();document.querySelector("#pairing-token").value="";state.authenticated=true;await health();await render();connectUpdates();}
async function health(){try{await coreNextIdentity();const h=await request("/health/ready");if(h.status!=="ready"||typeof h.version!=="string"||typeof h.backend!=="string")throw new Error("The address did not return a DRAGONHYDRA server health contract.");document.querySelector("#service-state").textContent=`Server ${h.status||"ready"} · ${h.backend||"local"}`;document.querySelector("#health-dot").className="dot ready";state.authenticated=true;}catch(err){document.querySelector("#service-state").textContent="Server unavailable";document.querySelector("#health-dot").className="dot failed";}}
function connectUpdates(){if(state.stream||!state.authenticated)return;const source=new EventSource(API+"/updates",{withCredentials:true});state.stream=source;source.onopen=()=>{document.querySelector("#footer-status").textContent="Update stream connected. Committed changes are available on refresh.";};for(const topic of ["data","update","import","export","job"])source.addEventListener(topic,()=>{document.querySelector("#footer-status").textContent="New committed data available. Refresh this view to load it.";});source.addEventListener("resync",()=>{document.querySelector("#footer-status").textContent="Update history expired. Refresh to synchronize retained data.";});source.onerror=()=>{document.querySelector("#footer-status").textContent="Update stream reconnecting. Manual refresh remains available.";};}
for(const [id,icon,label]of navItems)document.querySelector("#navigation").append(el("a",{class:"nav-item",href:`#${id}`,"data-route":id},el("span",{class:"nav-icon","aria-hidden":"true"},icon),label));
document.querySelector("#administration").addEventListener("click",openAdministration);
document.querySelector('a.skip[href="#main"]').addEventListener("click",skipToMain);
document.querySelector("#refresh").addEventListener("click",async()=>{await health();await render();});
document.querySelector("#login-form").addEventListener("submit",async ev=>{ev.preventDefault();const b=ev.currentTarget.querySelector("button");b.disabled=true;try{const remote=document.querySelector("#server-address").value.trim();if(remote){const target=new URL(remote);if(!["http:","https:"].includes(target.protocol))throw new Error("Use an HTTP or HTTPS server address.");if(target.username||target.password)throw new Error("Enter a server address without embedded credentials.");if(target.protocol==="http:"&&!["localhost","127.0.0.1","[::1]"].includes(target.hostname))throw new Error("A remote server requires HTTPS. Configure a trusted gateway endpoint.");if(target.origin===location.origin&&target.pathname===location.pathname){await login(document.querySelector("#pairing-token").value);document.querySelector("#login-error").textContent="";return;}throw new Error("Open the CORE NEXT server directly before pairing. Credential handoff to another origin is disabled.");}await login(document.querySelector("#pairing-token").value);document.querySelector("#login-error").textContent="";}catch(err){document.querySelector("#login-error").textContent=err.message;}finally{b.disabled=false;}});
document.querySelector("#login-dialog").addEventListener("cancel",ev=>ev.preventDefault());
window.addEventListener("hashchange",async()=>{if(location.hash.startsWith("#token=")){const token=new URLSearchParams(location.hash.slice(1)).get("token");history.replaceState(null,"",location.pathname+location.search+"#today");try{await login(token);}catch(err){state.authenticated=false;showLogin();document.querySelector("#login-error").textContent=err.message;}}else render();});
window.addEventListener("scroll",()=>state.scrolls.set(state.lastHash,window.scrollY),{passive:true});
window.addEventListener("beforeunload",()=>state.stream?.close());
(async()=>{if(new URLSearchParams(location.search).get("client")==="unpaired"){document.querySelector("#service-state").textContent="Connection required";showLogin();return;}const params=new URLSearchParams(location.hash.slice(1));const token=params.get("token");if(token){history.replaceState(null,"",location.pathname+location.search+"#today");try{await login(token);}catch(err){showLogin();document.querySelector("#login-error").textContent=err.message;}}else{await health();await render();if(state.authenticated)connectUpdates();}})();

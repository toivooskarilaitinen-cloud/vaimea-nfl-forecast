const teamNames={ARI:'Arizona',ATL:'Atlanta',BAL:'Baltimore',BUF:'Buffalo',CAR:'Carolina',CHI:'Chicago',CIN:'Cincinnati',CLE:'Cleveland',DAL:'Dallas',DEN:'Denver',DET:'Detroit',GB:'Green Bay',HOU:'Houston',IND:'Indianapolis',JAX:'Jacksonville',KC:'Kansas City',LV:'Las Vegas',LAC:'LA Chargers',LA:'LA Rams',LAR:'LA Rams',MIA:'Miami',MIN:'Minnesota',NE:'New England',NO:'New Orleans',NYG:'NY Giants',NYJ:'NY Jets',PHI:'Philadelphia',PIT:'Pittsburgh',SEA:'Seattle',SF:'San Francisco',TB:'Tampa Bay',TEN:'Tennessee',WAS:'Washington'};
const fmt=p=>`${Math.round(Number(p)*100)} %`;
function renderForecasts(data){const games=Array.isArray(data.forecasts)?data.forecasts:[];if(!games.length)return;document.querySelector('#forecastCount').textContent=games.length;document.querySelector('#statusLabel').textContent='PÄIVITETTY';document.querySelector('#updatedAt').textContent=`Lukittu ${new Date(data.cutoff).toLocaleString('fi-FI',{dateStyle:'medium',timeStyle:'short'})} · Malli ${data.model_version}`;document.querySelector('#forecastGrid').innerHTML=games.map(g=>{const hp=Number(g.home_win_probability);return `<article class="game-card"><div class="team"><span>VIERAS</span><strong>${teamNames[g.away_team]||g.away_team}</strong></div><div><div class="probbar"><i style="width:${(1-hp)*100}%"></i></div><div class="prob-labels"><b>${fmt(1-hp)}</b><b>${fmt(hp)}</b></div></div><div class="team"><span>KOTI</span><strong>${teamNames[g.home_team]||g.home_team}</strong></div></article>`}).join('')}
fetch('./public/data/latest.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderForecasts).catch(()=>{});

const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function renderStatus(data){const node=document.querySelector('#operationsStatus');if(!node)return;const fetched=data.data_fetched_at?new Date(data.data_fetched_at).toLocaleString('fi-FI',{dateStyle:'medium',timeStyle:'short'}):'ei vielä tuotantoajoa';const week=data.source_week??'—';const warnings=Array.isArray(data.warnings)?data.warnings.length:0;node.textContent=`Data haettu: ${fetched} · lähdeviikko ${week} · ledger-rivejä ${data.ledger_entries??0} · varoituksia ${warnings}`;}
fetch('./public/data/status.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderStatus).catch(()=>{});

function renderMovers(rows){const panel=document.querySelector('#moversPanel');if(!panel||!Array.isArray(rows)||!rows.length)return;panel.hidden=false;document.querySelector('#moversList').innerHTML=rows.map(row=>`<article class="content-card"><span class="meta">${esc(row.game_id)}</span><h2>${Number(row.move)>=0?'+':''}${(Number(row.move)*100).toFixed(1)} %-yks.</h2><p>${esc(row.move_reason)}</p><span class="arrow">${fmt(row.home_win_probability)}</span></article>`).join('');}
fetch('./public/data/movers.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderMovers).catch(()=>{});

function renderReview(data){const panel=document.querySelector('#reviewPanel');if(!panel)return;panel.hidden=false;const games=Array.isArray(data.games)?data.games:[];document.querySelector('#reviewGames').innerHTML=games.map(game=>`<article class="review-game"><strong>${esc(game.away_team)} @ ${esc(game.home_team)}</strong><span>${esc(game.away_qb_id)} / ${esc(game.home_qb_id)}</span><span>${fmt(game.home_win_probability)} koti</span></article>`).join('')||'<p>Ei valmisteltua ottelulistaa.</p>';const issues=[...(data.errors||[]),...(data.warnings||[])];document.querySelector('#reviewIssues').innerHTML=issues.map(item=>`<li>${esc(item)}</li>`).join('')||'<li>Kaikki julkaisuportit kunnossa.</li>';}
fetch('./public/data/review.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderReview).catch(()=>{});

function renderPerformance(data){if(!document.querySelector('#brierMetric'))return;document.querySelector('#brierMetric').textContent=Number(data.model.brier).toFixed(3);document.querySelector('#logLossMetric').textContent=Number(data.model.log_loss).toFixed(3);document.querySelector('#rollingMetric').textContent=Number(data.rolling.brier).toFixed(3);document.querySelector('#scoredGames').textContent=data.model.games;}
fetch('./public/data/performance.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderPerformance).catch(()=>{});

function renderBacktest(data){
  const metrics=document.querySelector('#backtestMetrics');
  if(!metrics||!data?.metrics)return;
  const values=[data.metrics.brier,data.metrics.log_loss,data.metrics.games,data.metrics.baseline_brier];
  metrics.querySelectorAll('strong').forEach((node,index)=>{node.textContent=index===2?values[index]:Number(values[index]).toFixed(3)});
  document.querySelector('#modelComparison').textContent=Number(data.metrics.brier).toFixed(3);
  document.querySelector('#baselineComparison').textContent=Number(data.metrics.baseline_brier).toFixed(3);
  const chart=document.querySelector('#calibrationChart');
  const bins=Array.isArray(data.calibration)?data.calibration:[];
  chart.innerHTML=bins.map(bin=>{
    const predicted=Number(bin.predicted)*100;
    const observed=Number(bin.observed)*100;
    const label=String(bin.bin).replace(/[\[\]()]/g,'');
    return `<div class="calibration-row"><span>${esc(label)}</span><div class="calibration-bars"><i class="predicted" style="width:${predicted}%" title="Ennustettu ${predicted.toFixed(1)} %"></i><i class="observed" style="width:${observed}%" title="Toteutunut ${observed.toFixed(1)} %"></i></div><strong>${predicted.toFixed(0)} / ${observed.toFixed(0)} %</strong><small>n=${Number(bin.n)}</small></div>`;
  }).join('');
}
fetch('./public/data/backtest-2025-v011-calibrated.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderBacktest).catch(()=>{});

const seasonMetrics={
  playoff_probability:'Playoff-todennäköisyys',
  division_probability:'Divisioonavoiton todennäköisyys',
  conference_probability:'Konferenssivoiton todennäköisyys',
  super_bowl_probability:'Super Bowl -todennäköisyys'
};
const chartColors=['#d17a3f','#f1e8df','#c49a72','#8fa3a0','#d6a44b','#a889bd','#77a56a','#c96f64'];
let seasonState=null;
let seasonMetric='super_bowl_probability';
let selectedSeasonTeams=new Set();
let selectedTeam=null;
const pointLabel=snapshot=>String(snapshot.week).toUpperCase()==='PRE'?'Pre':`W${snapshot.week}`;
const probabilityValue=(row,metric)=>row?.[metric]===null||row?.[metric]===undefined?null:Number(row[metric]);
function svgLineChart(series,snapshots,label,maxOverride=null){
  const width=900,height=360,left=55,right=22,top=24,bottom=52;
  const values=series.flatMap(item=>item.values.filter(value=>value!==null));
  if(!values.length)return '<div class="chart-empty">Tälle mittarille ei ole vielä luotettavaa dataa.</div>';
  const maxValue=maxOverride||Math.max(.1,Math.ceil(Math.max(...values)*20)/20);
  const x=index=>snapshots.length===1?(left+width-right)/2:left+index*(width-left-right)/(snapshots.length-1);
  const y=value=>top+(maxValue-value)*(height-top-bottom)/maxValue;
  const grid=Array.from({length:5},(_,index)=>{const value=maxValue*(4-index)/4;const py=y(value);return `<line x1="${left}" x2="${width-right}" y1="${py}" y2="${py}"/><text x="${left-10}" y="${py+4}" text-anchor="end">${(value*100).toFixed(value<.1?1:0)}%</text>`}).join('');
  const labels=snapshots.map((snapshot,index)=>`<text x="${x(index)}" y="${height-18}" text-anchor="middle">${esc(pointLabel(snapshot))}</text>`).join('');
  const paths=series.map((item,index)=>{const color=item.color||chartColors[index%chartColors.length];let started=false;const commands=item.values.map((value,point)=>{if(value===null){started=false;return ''}const command=started?'L':'M';started=true;return `${command}${x(point).toFixed(1)},${y(value).toFixed(1)}`}).join(' ');const points=item.values.map((value,point)=>value===null?'':`<circle cx="${x(point)}" cy="${y(value)}" r="3.5"><title>${esc(item.name)} · ${esc(pointLabel(snapshots[point]))} · ${(value*100).toFixed(1)} %</title></circle>`).join('');return `<g style="--series:${color}"><path d="${commands}"/>${points}</g>`}).join('');
  return `<svg viewBox="0 0 ${width} ${height}" aria-label="${esc(label)}"><g class="chart-grid">${grid}${labels}</g><g class="chart-lines">${paths}</g></svg>`;
}
function latestTeamRows(data){return Array.isArray(data.latest?.teams)?[...data.latest.teams]:[]}
function availableMetric(data,metric){return Boolean(data.availability?.[metric])}
function chooseInitialMetric(data){return availableMetric(data,'super_bowl_probability')?'super_bowl_probability':'playoff_probability'}
function teamSeries(data,team,metric){return data.snapshots.map(snapshot=>probabilityValue(snapshot.teams.find(row=>row.team===team),metric))}
function renderSeasonLeague(){
  const rows=latestTeamRows(seasonState).sort((a,b)=>(probabilityValue(b,seasonMetric)??-1)-(probabilityValue(a,seasonMetric)??-1));
  document.querySelector('#historyMetricTitle').textContent=seasonMetrics[seasonMetric];
  const ranking=document.querySelector('#leagueRanking');
  ranking.innerHTML=rows.map((row,index)=>{const value=probabilityValue(row,seasonMetric);const selected=selectedSeasonTeams.has(row.team);return `<button type="button" data-team="${esc(row.team)}" class="ranking-row${selected?' selected':''}" ${value===null?'disabled':''}><span>${String(index+1).padStart(2,'0')}</span><strong>${esc(teamNames[row.team]||row.team)}</strong><i><b style="width:${value===null?0:value*100}%"></b></i><em>${value===null?'—':(value*100).toFixed(1)+' %'}</em></button>`}).join('');
  ranking.querySelectorAll('button:not([disabled])').forEach(button=>button.addEventListener('click',()=>{const team=button.dataset.team;if(selectedSeasonTeams.has(team))selectedSeasonTeams.delete(team);else selectedSeasonTeams.add(team);renderSeasonLeague()}));
  const series=[...selectedSeasonTeams].map((team,index)=>({name:teamNames[team]||team,color:chartColors[index%chartColors.length],values:teamSeries(seasonState,team,seasonMetric)}));
  document.querySelector('#probabilityChart').innerHTML=svgLineChart(series,seasonState.snapshots,seasonMetrics[seasonMetric]);
  document.querySelector('#chartLegend').innerHTML=series.map(item=>`<span style="--series:${item.color}"><i></i>${esc(item.name)}</span>`).join('');
}
function renderTeamForecast(){
  const latest=latestTeamRows(seasonState);const row=latest.find(item=>item.team===selectedTeam)||latest[0];if(!row)return;selectedTeam=row.team;
  document.querySelector('#teamForecastSelect').value=selectedTeam;document.querySelector('#teamForecastName').textContent=teamNames[selectedTeam]||selectedTeam;
  const metrics=Object.keys(seasonMetrics);document.querySelector('#teamProbabilityCards').innerHTML=metrics.map(metric=>{const value=probabilityValue(row,metric);const previous=seasonState.snapshots.length>1?probabilityValue(seasonState.snapshots.at(-2).teams.find(item=>item.team===selectedTeam),metric):null;const move=value!==null&&previous!==null?value-previous:null;return `<div><span>${esc(seasonMetrics[metric])}</span><strong>${value===null?'—':(value*100).toFixed(1)+' %'}</strong><small>${move===null?'ei vielä historiaa':`${move>=0?'↑':'↓'} ${Math.abs(move*100).toFixed(1)} pp`}</small></div>`}).join('');
  const series=metrics.filter(metric=>availableMetric(seasonState,metric)).map((metric,index)=>({name:seasonMetrics[metric],color:chartColors[index],values:teamSeries(seasonState,selectedTeam,metric)}));
  document.querySelector('#teamProbabilityChart').innerHTML=svgLineChart(series,seasonState.snapshots,`${teamNames[selectedTeam]||selectedTeam} probability history`);
}
function renderSeasonHistory(data){
  if(!document.querySelector('#seasonDashboard')||!Array.isArray(data.snapshots)||!data.snapshots.length)return;
  seasonState=data;seasonMetric=chooseInitialMetric(data);document.querySelector('#seasonEmpty').hidden=true;document.querySelector('#seasonDashboard').hidden=false;
  const latest=data.latest;document.querySelector('#seasonUpdated').textContent=`${pointLabel(latest)} · ${new Date(latest.as_of).toLocaleString('fi-FI',{dateStyle:'medium',timeStyle:'short'})}`;
  const tabs=document.querySelectorAll('#forecastTabs button');tabs.forEach(button=>{const available=availableMetric(data,button.dataset.metric);button.disabled=!available;button.classList.toggle('active',button.dataset.metric===seasonMetric);button.addEventListener('click',()=>{seasonMetric=button.dataset.metric;tabs.forEach(item=>item.classList.toggle('active',item===button));renderSeasonLeague()})});
  const unavailable=Object.entries(seasonMetrics).filter(([metric])=>!availableMetric(data,metric)).map(([,label])=>label);document.querySelector('#metricAvailability').textContent=unavailable.length?`${unavailable.join(' ja ')} avautuvat, kun pudotuspelikaavion ottelumalli on käytössä.`:'';
  const rows=latestTeamRows(data).sort((a,b)=>(probabilityValue(b,seasonMetric)??-1)-(probabilityValue(a,seasonMetric)??-1));selectedSeasonTeams=new Set(rows.slice(0,4).map(row=>row.team));selectedTeam=rows[0]?.team;
  const select=document.querySelector('#teamForecastSelect');select.innerHTML=[...rows].sort((a,b)=>(teamNames[a.team]||a.team).localeCompare(teamNames[b.team]||b.team,'fi')).map(row=>`<option value="${esc(row.team)}">${esc(teamNames[row.team]||row.team)}</option>`).join('');select.addEventListener('change',()=>{selectedTeam=select.value;renderTeamForecast()});renderSeasonLeague();renderTeamForecast();
}
fetch('./public/data/season-history.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(renderSeasonHistory).catch(()=>{});

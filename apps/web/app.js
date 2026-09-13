const $ = s => document.querySelector(s);
const money = n => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n||0);
const zoneLabel = z => ({EXCLUSIVE:'独占区',ADVANTAGE:'优质区',HOMOGENEOUS:'同质区'}[z]||z);
const esc = s => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function getJSON(url, options){ const r=await fetch(url, options); if(!r.ok) throw new Error(await r.text()); return r.json(); }

function initNav(){
  document.querySelectorAll('.nav').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active')); btn.classList.add('active');
    document.querySelectorAll('.view').forEach(x=>x.classList.remove('active-view'));
    $('#'+btn.dataset.view).classList.add('active-view');
    $('#page-title').textContent=btn.textContent;
    if(btn.dataset.view==='opportunities') loadOpportunities();
    if(btn.dataset.view==='products') loadProducts();
    if(btn.dataset.view==='workforce') loadWorkforce();
    if(btn.dataset.view==='datahub') loadDataHub();
    if(btn.dataset.view==='commerce') loadCommerce();
    if(btn.dataset.view==='philosophy') loadPhilosophy();
  }));
}

async function loadDashboard(){
  const d=await getJSON('/api/dashboard'); const k=d.kpis;
  const items=[['GMV',money(k.gmv)],['Contribution Profit',money(k.contribution_profit)],['Margin',k.contribution_margin_pct+'%'],['Master Products',k.active_products],['Candidates',k.candidate_products],['SCALE Candidates',k.scale_candidates]];
  $('#kpis').innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');
  const maxZone=Math.max(...Object.values(d.zone_counts),1);
  $('#zone-bars').innerHTML=['EXCLUSIVE','ADVANTAGE','HOMOGENEOUS'].map(z=>`<div class="zone-row ${z.toLowerCase()}"><span>${zoneLabel(z)}</span><div class="bar"><i style="width:${d.zone_counts[z]/maxZone*100}%"></i></div><strong>${d.zone_counts[z]}</strong></div>`).join('');
  const pipeOrder=['DISCOVERED','EVALUATED','PROMOTED','REJECTED'];
  const maxPipe=Math.max(...Object.values(d.candidate_pipeline),1);
  $('#pipeline-bars').innerHTML=pipeOrder.map(s=>`<div class="channel-row"><span>${s}</span><div class="bar"><i style="width:${(d.candidate_pipeline[s]||0)/maxPipe*100}%"></i></div><strong>${d.candidate_pipeline[s]||0}</strong></div>`).join('');
  const maxCh=Math.max(...Object.values(d.channel_sales),1);
  $('#channel-sales').innerHTML=Object.entries(d.channel_sales).map(([c,v])=>`<div class="channel-row"><span>${esc(c)}</span><div class="bar"><i style="width:${v/maxCh*100}%"></i></div><strong>${money(v)}</strong></div>`).join('');
  $('#ceo-decisions').innerHTML=d.ceo_decisions.length?d.ceo_decisions.map(t=>taskHtml(t,true)).join(''):'<div class="empty-state">暂无待审批事项</div>';
  bindTaskActions();
  if(d.operating_os){
    const os=d.operating_os;
    const mix=os.mix||{};
    $('#mix-contradiction').innerHTML=`<strong>${esc(os.phase||'')}</strong> · ${esc(os.main_contradiction||'')}<br/>组合毛利 ${mix.current_blended_margin_pct??'—'}% → 目标配比推演 ${mix.target_blended_margin_pct??'—'}%${(os.management&&os.management.ceo_agenda&&os.management.ceo_agenda[2])?'<br/>'+esc(os.management.ceo_agenda[2]):''}`;
  }
}

function taskHtml(t,decision){return `<div class="task" data-task-id="${t.id}"><div class="task-head"><strong>${esc(t.agent)} · ${esc(t.title)}</strong><span class="tag ${t.priority==='HIGH'?'high':''}">${esc(t.talent_label||t.priority)}</span></div><p>${esc(t.recommendation||'')}</p>${decision?'<div class="decision-actions"><button class="approve" data-task-action="APPROVE">批准</button><button data-task-action="REJECT">拒绝</button><button data-task-action="REEVALUATE">重新分析</button></div>':''}</div>`}

function bindTaskActions(){
  document.querySelectorAll('[data-task-action]').forEach(btn=>btn.onclick=async()=>{
    const task=btn.closest('[data-task-id]');
    await getJSON(`/api/agent-tasks/${task.dataset.taskId}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:btn.dataset.taskAction,note:''})});
    await Promise.all([loadDashboard(),loadWorkforce()]);
  });
}

async function loadProducts(){
  const rows=await getJSON('/api/products');
  $('#listing-pack-product').innerHTML=rows.map(p=>`<option value="${p.id}">${esc(p.sku)} · ${esc(p.name)}</option>`).join('');
  $('#product-table').innerHTML=rows.map((p,i)=>`<tr><td>${esc(p.sku)}</td><td><strong>${esc(p.name)}</strong><div class="muted">${esc(p.target_market)} · ${money(p.retail_price)}</div></td><td>${unitChip(p.product_unit)}</td><td><span class="zone-badge zone-${p.zone}">${zoneLabel(p.zone)}</span></td><td><strong>${p.opportunity_score}</strong></td><td>${p.expected_margin_pct}%</td><td><span class="decision-badge decision-${p.decision}">${p.decision}</span></td><td>${i===0?`<button class="approve" data-publish-shopify="${p.id}">Draft</button> <button data-pack="${p.id}">上架包</button>`:`<button data-pack="${p.id}">上架包</button>`}</td></tr>`).join('');
  document.querySelectorAll('[data-publish-shopify]').forEach(btn=>btn.onclick=async()=>{
    btn.disabled=true;
    try{
      const r=await getJSON(`/api/channels/shopify/publish_master/${btn.dataset.publishShopify}`,{method:'POST'});
      alert(`${r.status}: ${r.master_sku||''}\n${r.admin_url||(r.data&&r.data.admin_url)||r.reason||r.listing_status||''}`);
      await loadProducts();
    }catch(err){alert(String(err));}
    finally{btn.disabled=false;}
  });
  document.querySelectorAll('[data-pack]').forEach(btn=>btn.onclick=()=>runListingPack(btn.dataset.pack));
}

async function runListingPack(productId){
  setResult('#listing-pack-result','正在生成文案、渠道主图和短视频分镜…');
  try{
    const d=await getJSON(`/api/content/pack/${productId}`,{method:'POST'});
    const imgs=d.images&&d.images.channels||{};
    const v=d.video||{};
    const links=Object.entries(imgs).map(([ch,info])=>`${ch} ${info.url||''}`).join(' · ');
    setResult('#listing-pack-result',`${d.master_sku} · 图 ${d.images.origin}/${d.images.cutout} · 视频 ${v.status}${v.video_url?` · ${v.video_url}`:''} · ${links}`,true);
  }catch(err){setResult('#listing-pack-result',String(err),false)}
}

async function loadWorkforce(){ const rows=await getJSON('/api/agent-tasks'); $('#workforce-list').innerHTML=rows.map(t=>taskHtml(t,t.requires_ceo_approval&&t.status==='OPEN')).join(''); bindTaskActions(); }

const sliderDefs=[
 ['uniqueness','产品独特性',60],['channel_control','渠道控制力',55],['cost_advantage','成本优势',65],['supply_advantage','供应优势',70],['content_advantage','内容优势',75],['brand_advantage','品牌优势',45],['market_demand','市场需求',78],['competition_intensity','竞争强度',60],['compliance_risk','合规风险',30],['return_risk','退货风险',30]
];
function sliderHTML(prefix=''){
  return sliderDefs.map(([n,l,v])=>`<label><span>${l}</span><div class="slider-line"><input name="${prefix}${n}" type="range" min="0" max="100" value="${v}"/><span class="slider-value" data-for="${prefix}${n}">${v}</span></div></label>`).join('');
}
function bindSliders(root=document){ root.querySelectorAll('input[type=range]').forEach(x=>x.addEventListener('input',()=>{const el=document.querySelector(`[data-for="${x.name}"]`); if(el) el.textContent=x.value;})); }

function initSelection(){
  $('#sliders').innerHTML=sliderHTML(); bindSliders($('#selection-form'));
  $('#selection-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target); const payload={};
    payload.product_name=f.get('product_name'); payload.exclusive_rights=f.get('exclusive_rights')==='on';
    payload.has_persona=f.get('has_persona')==='on'; payload.memory_enabled=f.get('memory_enabled')==='on';
    payload.hw_gen=Number(f.get('hw_gen')||1); payload.claimed_features=claimedFeatures(f);
    sliderDefs.forEach(([n])=>payload[n]=Number(f.get(n))); payload.expected_margin_pct=Number(f.get('expected_margin_pct')); payload.cash_cycle_days=Number(f.get('cash_cycle_days'));
    const r=await getJSON('/api/selection/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('#selection-result').className='';
    const ph=r.philosophy;
    const phHtml=ph?`<div class="philosophy-box"><p class="eyebrow">经营哲学</p><p><span class="status-chip">${esc(ph.advantage_quality_label)}</span> 靠谱 ${ph.reliability_score}</p><p><strong>主要矛盾</strong> ${esc(ph.main_contradiction)}</p><p><strong>谋略</strong> ${esc(ph.strategy)}</p><p><strong>落地</strong> ${esc(ph.implementation)}</p><p><strong>博弈</strong> ${esc(ph.gaming_move_label)}</p></div>`:'';
    const cbHtml=r.crossborder?`<div class="philosophy-box"><p class="eyebrow">跨境 AI 玩具</p><p>${esc(r.crossborder.archetype_label||'')} · ${esc(r.crossborder.market||'')} · ${esc(r.crossborder.channel||'')}</p><p>${esc(r.crossborder.customer_fundamentals||'')}</p><ul class="result-list">${(r.crossborder.ops_actions||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'';
    $('#selection-result').innerHTML=`<div class="result-hero"><div class="result-zone">${r.zone_label} <span class="decision-badge decision-${r.decision}">${r.decision}</span></div><div class="score">${r.opportunity_score}<small> / 100 Opportunity Score</small></div></div><div class="metric-grid"><div class="metric"><small>独占分</small><strong>${r.exclusive_score}</strong></div><div class="metric"><small>优势分</small><strong>${r.advantage_score}</strong></div><div class="metric"><small>风险分</small><strong>${r.risk_score}</strong></div></div>${phHtml}${cbHtml}<p class="eyebrow">WHY</p><ul class="result-list">${r.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p class="eyebrow">NEXT ACTIONS</p><ul class="result-list">${r.recommended_actions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
  });
}

function initCandidateForm(){
  $('#candidate-sliders').innerHTML=sliderHTML('c_'); bindSliders($('#candidate-form'));
  $('#candidate-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target);
    const payload={
      product_name:f.get('product_name'), supplier_name:f.get('supplier_name'), supplier_sku:f.get('supplier_sku'), market:f.get('market'), recommended_channel:f.get('recommended_channel'),
      supplier_price:Number(f.get('supplier_price')), estimated_landed_cost:Number(f.get('estimated_landed_cost')), target_retail_price:Number(f.get('target_retail_price')), exclusive_rights:f.get('exclusive_rights')==='on',
      has_persona:f.get('has_persona')==='on', memory_enabled:f.get('memory_enabled')==='on', hw_gen:Number(f.get('hw_gen')||1), shell:f.get('shell')||'', claimed_features:claimedFeatures(f),
      source:'Manual Supplier Pool', cash_cycle_days:30
    };
    sliderDefs.forEach(([n])=>payload[n]=Number(f.get('c_'+n)));
    await getJSON('/api/candidates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    await Promise.all([loadOpportunities(),loadDashboard()]);
  });
  $('#refresh-opportunities').onclick=loadOpportunities;
}

async function loadOpportunities(){
  const d=await getJSON('/api/opportunities');
  const s=d.summary;
  $('#opportunity-kpis').innerHTML=[['Market Signals',s.signals],['Candidates',s.candidates],['SCALE',s.scale],['TEST',s.test],['独占区',s.exclusive]].map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');
  $('#market-pulse').innerHTML=d.market_pulse.length?d.market_pulse.map(p=>`<div class="pulse-card"><div><strong>${esc(p.market)} · ${esc(p.channel)}</strong><small>需求 ${p.demand_score} · 增长 ${p.growth_score}</small></div><div class="pulse-score">${p.growth_score}</div><div class="mini-bar"><i style="width:${p.growth_score}%"></i></div><span class="risk-text">竞争 ${p.competition_score}</span></div>`).join(''):'<div class="empty-state">还没有市场信号</div>';
  $('#candidate-table').innerHTML=d.candidates.map(c=>candidateRow(c)).join('');
  bindCandidateActions();
}

function candidateRow(c){
  const locked=c.status==='PROMOTED'||c.status==='REJECTED';
  return `<tr data-candidate-id="${c.id}"><td><strong>${esc(c.product_name)}</strong><div class="muted">${esc(c.candidate_code)} · ${esc(c.supplier_name)}${c.philosophy?` · ${esc(c.philosophy.advantage_quality_label)}`:''}</div><div class="muted">${unitChip(c.product_unit)}</div></td><td>${esc(c.market)}<div class="muted">${esc(c.recommended_channel)}</div></td><td><span class="zone-badge zone-${c.zone}">${zoneLabel(c.zone)}</span></td><td><strong>${c.opportunity_score}</strong></td><td>${c.expected_margin_pct}%</td><td>${c.risk_score}</td><td><span class="decision-badge decision-${c.decision}">${c.decision}</span></td><td><span class="status-chip">${esc(c.status)}</span></td><td>${locked?'<span class="muted">已完成</span>':`<div class="row-actions"><button class="approve" data-candidate-action="APPROVE">批准</button><button data-candidate-action="REEVALUATE">重评</button><button class="danger" data-candidate-action="REJECT">淘汰</button></div>`}</td></tr>`;
}

function claimedFeatures(f){
  const feats=['mic','speaker','network'];
  if(f.get('claim_camera')==='on') feats.push('camera');
  if(f.get('claim_limb')==='on') feats.push('limb','servo');
  return feats;
}

function unitChip(u){
  if(!u) return '<span class="muted">无护照</span>';
  const soul=u.has_companion_soul?'魂齐':'无魂';
  const gap=(u.cert_gap||[]).length?`缺口 ${u.cert_gap.join('/')}`:'cert_ok';
  const hw=u.needs_hardware_gate?'硬件门禁':'Gen'+u.hw_gen;
  return `${soul} · ${hw} · ${gap}`;
}

function bindCandidateActions(){
  document.querySelectorAll('[data-candidate-action]').forEach(btn=>btn.onclick=async()=>{
    const row=btn.closest('[data-candidate-id]');
    btn.disabled=true;
    try{
      await getJSON(`/api/candidates/${row.dataset.candidateId}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:btn.dataset.candidateAction,note:''})});
      await Promise.all([loadOpportunities(),loadDashboard(),loadProducts(),loadWorkforce()]);
    } finally { btn.disabled=false; }
  });
}



function setResult(el, text, ok=true){
  const target=typeof el==='string'?$(el):el;
  target.textContent=text;
  target.classList.remove('pipeline-ok','pipeline-fail');
  target.classList.add(ok?'pipeline-ok':'pipeline-fail');
}

async function uploadForm(form, url){
  const fd=new FormData(form);
  const r=await fetch(url,{method:'POST',body:fd});
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

async function loadDataHub(){
  const [d,candidates]=await Promise.all([getJSON('/api/data-pipeline'),getJSON('/api/candidates')]);
  $('#data-kpis').innerHTML=[['Import Batches',d.counts.batches],['Product Assets',d.counts.assets],['AI Analyses',d.counts.analyses],['Market Signals',d.counts.market_signals]].map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');
  const mm=d.multimodal;
  $('#mm-provider').textContent=mm.real_vision_configured?`REAL · ${mm.model}`:'LOCAL · 未配置视觉模型';
  $('#mm-provider').className='status-chip '+(mm.real_vision_configured?'pipeline-ok':'');
  $('#asset-candidate').innerHTML=candidates.map(c=>`<option value="${c.id}">${esc(c.product_name)} · ${zoneLabel(c.zone)} · ${c.decision}</option>`).join('');
  $('#batch-list').innerHTML=d.batches.length?d.batches.map(b=>`<div class="pipeline-item"><strong>${esc(b.batch_type)} · ${esc(b.filename)}</strong><small class="${b.status.includes('FAILED')?'pipeline-fail':'pipeline-ok'}">${esc(b.status)} · ${b.accepted_records}/${b.total_records} accepted${b.rejected_records?` · ${b.rejected_records} rejected`:''}</small></div>`).join(''):'<div class="empty-state">还没有真实数据导入批次</div>';
  const analyses=d.analyses.map(a=>`<div class="pipeline-item"><strong>Multimodal · Candidate #${a.candidate_id}</strong><small class="${a.status==='DONE'?'pipeline-ok':'pipeline-fail'}">${esc(a.provider)} ${esc(a.model||'')} · confidence ${a.confidence} · ${esc(a.status)}</small></div>`);
  const runs=d.connector_runs.map(r=>`<div class="pipeline-item"><strong>${esc(r.connector)} · ${esc(r.market)}</strong><small class="${r.status==='COMPLETED'?'pipeline-ok':r.status==='FAILED'?'pipeline-fail':''}">${esc(r.status)} · ${r.records_received} signals${r.error_message?` · ${esc(r.error_message)}`:''}</small></div>`);
  $('#analysis-list').innerHTML=(analyses.concat(runs).join(''))||'<div class="empty-state">还没有分析或实时连接器运行</div>';
  try{
    const oss=await getJSON('/api/foundation');
    const pkgs=(oss.opensource&&oss.opensource.packages)||[];
    $('#oss-stack-list').innerHTML=pkgs.map(p=>`<div class="pipeline-item"><strong>${esc(p.id)} · ${esc(p.role)}</strong><small class="${p.cloned||p.mode==='pip'?'pipeline-ok':''}">${esc(p.mode)} · ${p.cloned?'cloned':(p.mode==='pip'?'pip':'missing')} · ${esc(p.license||'')}</small></div>`).join('')||'<div class="empty-state">运行 bootstrap_opensource 以克隆 vendor 参考实现</div>';
  }catch{ $('#oss-stack-list').innerHTML='<div class="empty-state">开源清单暂不可用</div>'; }
}

function initDataHub(){
  $('#supplier-import-form').addEventListener('submit',async e=>{
    e.preventDefault(); setResult('#supplier-import-result','正在导入并自动运行三区选品…');
    try{
      const d=await uploadForm(e.target,'/api/imports/supplier-catalog');
      setResult('#supplier-import-result',`完成：${d.accepted} accepted · ${d.rejected} rejected · batch #${d.batch_id}`);
      await Promise.all([loadDataHub(),loadOpportunities(),loadDashboard()]);
    }catch(err){setResult('#supplier-import-result',String(err),false)}
  });
  $('#market-import-form').addEventListener('submit',async e=>{
    e.preventDefault(); setResult('#market-import-result','正在导入市场数据并重评候选商品…');
    try{
      const d=await uploadForm(e.target,'/api/imports/market-signals');
      setResult('#market-import-result',`完成：${d.signals} signals · 自动重评 ${d.candidates_reevaluated} 个候选商品`);
      await Promise.all([loadDataHub(),loadOpportunities(),loadDashboard()]);
    }catch(err){setResult('#market-import-result',String(err),false)}
  });
  $('#trends-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target); const keywords=String(f.get('keywords')||'').split(',').map(x=>x.trim()).filter(Boolean);
    setResult('#trends-result','正在拉取 Google Trends 实时数据…');
    try{
      const d=await getJSON('/api/market/google-trends/pull',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({market:f.get('market'),keywords})});
      setResult('#trends-result',`完成：${d.signals.length} signals · 自动重评 ${d.candidates_reevaluated} 个候选商品`);
      await Promise.all([loadDataHub(),loadOpportunities()]);
    }catch(err){setResult('#trends-result',`实时连接失败：${err}`,false)}
  });
  $('#crawl-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target);
    const urls=String(f.get('urls')||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    const keywords=String(f.get('keywords')||'').split(',').map(x=>x.trim()).filter(Boolean);
    setResult('#crawl-result','正在抓取公开页（失败不造假）…');
    try{
      const d=await getJSON('/api/market/crawl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({market:f.get('market'),urls,keywords})});
      setResult('#crawl-result',`完成：${d.signals.length} 条弱信号 · 自动重评 ${d.candidates_reevaluated} 个候选\n来源 ${[...new Set(d.signals.map(s=>s.source))].join(', ')}`);
      await Promise.all([loadDataHub(),loadOpportunities(),loadDashboard()]);
    }catch(err){setResult('#crawl-result',`爬虫拒绝写入：${err}`,false)}
  });
  $('#asset-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target); const candidateId=f.get('candidate_id');
    setResult('#asset-result','正在上传商品图片/PDF…');
    try{
      const d=await uploadForm(e.target,`/api/candidates/${candidateId}/assets`);
      setResult('#asset-result',`已上传 ${d.uploaded.length} 个资产：${d.uploaded.map(x=>x.filename).join(', ')}`);
      await loadDataHub();
    }catch(err){setResult('#asset-result',String(err),false)}
  });
  async function analyze(provider){
    const candidateId=$('#asset-candidate').value; if(!candidateId) return;
    setResult('#asset-result',provider==='real'?'正在调用真实多模态视觉模型…':'正在运行本地结构化解析…');
    try{
      const d=await getJSON(`/api/candidates/${candidateId}/multimodal-analyze?provider=${provider}&apply=true`,{method:'POST'});
      const r=d.result||{};
      setResult('#asset-result',`${d.provider} 完成\n${r.summary||''}\nFeatures: ${(r.features||[]).slice(0,5).join(' / ')}\n三区已重评：${zoneLabel(d.candidate.zone)} · ${d.candidate.decision}`);
      await Promise.all([loadDataHub(),loadOpportunities(),loadDashboard()]);
    }catch(err){setResult('#asset-result',String(err),false)}
  }
  $('#analyze-local').onclick=()=>analyze('local');
  $('#analyze-real').onclick=()=>analyze('real');
  $('#refresh-datahub').onclick=loadDataHub;
}


async function loadCommerce(){
  const [d,products]=await Promise.all([getJSON('/api/commerce-control-center'),getJSON('/api/products')]);
  const s=d.summary;
  $('#commerce-kpis').innerHTML=[['Channel Accounts',s.channel_accounts],['Connected',s.connected_accounts],['Listings',s.active_or_submitted_listings],['Orders',s.orders],['GMV',money(s.gmv)],['Contribution',money(s.contribution_profit)]].map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');
  $('#channel-accounts').innerHTML=d.accounts.map(a=>`<div class="channel-account" data-channel-account="${a.id}"><div><strong>${esc(a.channel)} · ${esc(a.account_name)}</strong><small>${esc(a.market)} · ${esc(a.credential_env_prefix||'NO_PREFIX')}</small></div><span class="status-chip ${a.status==='CONNECTED'?'pipeline-ok':a.status==='ERROR'?'pipeline-fail':''}">${esc(a.status)}</span><button class="ghost" data-check-channel="${a.id}">检测连接</button><button class="ghost" data-sync-channel="${a.id}">同步订单</button>${a.last_error?`<p class="channel-error">${esc(a.last_error)}</p>`:''}</div>`).join('');
  const accountOptions=d.accounts.map(a=>`<option value="${a.id}">${esc(a.channel)} · ${esc(a.account_name)} · ${esc(a.status)}</option>`).join('');
  $('#publish-account').innerHTML=accountOptions; $('#sync-account').innerHTML=accountOptions;
  $('#publish-product').innerHTML=products.map(p=>`<option value="${p.id}">${esc(p.sku)} · ${esc(p.name)} · ${p.decision}</option>`).join('');
  $('#sku-profit-table').innerHTML=d.sku_profit.length?d.sku_profit.map(p=>`<tr><td><strong>${esc(p.sku)}</strong><div class="muted">${esc(p.title)}</div></td><td>${p.units}</td><td>${money(p.net_sales)}</td><td>${money(p.product_cost)}</td><td>${money(p.shipping_cost)}</td><td>${money(p.platform_fee)}</td><td>${money(p.ad_cost)}</td><td>${money(p.refund_cost)}</td><td><strong class="${p.contribution_profit>=0?'profit-positive':'profit-negative'}">${money(p.contribution_profit)}</strong></td><td>${p.contribution_margin_pct}%</td><td><span class="status-chip ${p.profit_quality==='RECONCILED'?'pipeline-ok':''}">${p.profit_quality}</span></td></tr>`).join(''):'<tr><td colspan="11" class="muted">订单回流后才会产生SKU利润</td></tr>';
  $('#channel-sync-list').innerHTML=d.sync_runs.length?d.sync_runs.map(r=>`<div class="pipeline-item"><strong>Account #${r.account_id} · ${esc(r.operation)}</strong><small class="${r.status==='DONE'?'pipeline-ok':r.status==='FAILED'?'pipeline-fail':''}">${esc(r.status)} · received ${r.received} · written ${r.written}${r.error?` · ${esc(r.error)}`:''}</small></div>`).join(''):'<div class="empty-state">还没有渠道同步记录</div>';
  bindCommerceActions();
}

function bindCommerceActions(){
  document.querySelectorAll('[data-check-channel]').forEach(btn=>btn.onclick=async()=>{
    btn.disabled=true; try{ const d=await getJSON(`/api/channels/${btn.dataset.checkChannel}/check`,{method:'POST'}); setResult('#sync-result',`连接检测：${d.status}${d.error?` · ${d.error}`:''}`,d.status==='CONNECTED'); await loadCommerce(); } finally {btn.disabled=false}
  });
  document.querySelectorAll('[data-sync-channel]').forEach(btn=>btn.onclick=async()=>{
    btn.disabled=true; try{ const d=await getJSON(`/api/channels/${btn.dataset.syncChannel}/orders/sync`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({since_hours:72})}); setResult('#sync-result',`订单同步：${d.status} · received ${d.received||0} · written ${d.written||0}`,d.status==='DONE'); await Promise.all([loadCommerce(),loadDashboard()]); } finally {btn.disabled=false}
  });
}

function initShopifyChannel(){
  const form=$('#shopify-connect-form');
  if(!form) return;
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    const f=new FormData(form);
    setResult('#shopify-connect-result','正在检测 Shopify Admin API…');
    try{
      const d=await getJSON('/api/channels/shopify/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shop_url:f.get('shop_url'),access_token:f.get('access_token')})});
      form.querySelector('[name="access_token"]').value='';
      setResult('#shopify-connect-result',`已连接 ${esc(d.shop&&d.shop.name||d.status)} · ${esc(d.store_domain||'')}`,d.status==='CONNECTED');
      await loadCommerce();
    }catch(err){setResult('#shopify-connect-result',String(err),false)}
  });
  const first=$('#shopify-publish-first');
  if(first) first.onclick=async()=>{
    setResult('#shopify-connect-result','正在把第一条 Master Product 打成 Shopify Draft…');
    try{
      const d=await getJSON('/api/channels/shopify/publish-first-master',{method:'POST'});
      const ok=['SUBMITTED','PUBLISHED'].includes(d.status);
      setResult('#shopify-connect-result',`${d.status}: ${d.master_sku||''} ${d.admin_url||d.external_listing_id||d.reason||''}`,ok);
      await Promise.all([loadCommerce(),loadProducts()]);
    }catch(err){setResult('#shopify-connect-result',String(err),false)}
  };
}

function initCommerce(){
  $('#channel-account-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target);
    const payload={channel:f.get('channel'),account_name:f.get('account_name'),market:f.get('market')||'US',credential_env_prefix:f.get('credential_env_prefix')||'',store_domain:f.get('store_domain')||'',seller_id:f.get('seller_id')||'',marketplace_id:f.get('marketplace_id')||'',shop_cipher:f.get('shop_cipher')||'',config:{}};
    try{ await getJSON('/api/channels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); setResult('#sync-result','渠道账号已创建；请在环境变量配置真实密钥后检测连接'); await loadCommerce(); }catch(err){setResult('#sync-result',String(err),false)}
  });
  $('#publish-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target); setResult('#publish-result','正在执行三区Gate并发布…');
    try{
      let channelPayload={}; const rawPayload=String(f.get('channel_payload')||'').trim(); if(rawPayload) channelPayload=JSON.parse(rawPayload);
      const d=await getJSON('/api/channels/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({master_product_id:Number(f.get('master_product_id')),channel_account_id:Number(f.get('channel_account_id')),publish_as_draft:f.get('publish_as_draft')==='on',channel_payload:channelPayload})});
      setResult('#publish-result',`发布结果：${d.status}${d.external_listing_id?` · ${d.external_listing_id}`:''}${d.reason?` · ${d.reason}`:''}`,['PUBLISHED','SUBMITTED'].includes(d.status)); await loadCommerce();
    }catch(err){setResult('#publish-result',String(err),false)}
  });
  $('#order-sync-form').addEventListener('submit',async e=>{
    e.preventDefault(); const f=new FormData(e.target); setResult('#sync-result','正在拉取渠道订单并对账…');
    try{ const d=await getJSON(`/api/channels/${f.get('account_id')}/orders/sync`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({since_hours:Number(f.get('since_hours'))})}); setResult('#sync-result',`完成：${d.received||0} received · ${d.written||0} written`,d.status==='DONE'); await Promise.all([loadCommerce(),loadDashboard()]); }catch(err){setResult('#sync-result',String(err),false)}
  });
  $('#cost-import-form').addEventListener('submit',async e=>{
    e.preventDefault(); setResult('#cost-result','正在导入真实成本并按订单/SKU归集…');
    try{ const d=await uploadForm(e.target,'/api/costs/import'); setResult('#cost-result',`完成：${d.accepted} accepted · ${d.rejected} rejected · ${d.reconciliation.orders_reconciled} orders reconciled`); await Promise.all([loadCommerce(),loadDashboard()]); }catch(err){setResult('#cost-result',String(err),false)}
  });
  $('#refresh-commerce').onclick=loadCommerce;
}

function mixStack(title, share){
  const order=[['HOMOGENEOUS','同质区'],['ADVANTAGE','优质区'],['EXCLUSIVE','独占区']];
  return `<div class="mix-col"><div class="mix-stack">${order.map(([z,l])=>`<div class="mix-seg mix-${z.toLowerCase()}" style="flex:${Math.max(share[z]||0,1)}">${l} ${share[z]||0}%</div>`).join('')}</div><small>${esc(title)}</small></div>`;
}

async function loadPhilosophy(){
  const os=await getJSON('/api/operating-os');
  const mix=os.mix;
  $('#os-phase').textContent=os.phase;
  $('#os-contradiction').textContent=os.main_contradiction;
  $('#os-fundamentals').textContent=os.customer_fundamentals;
  $('#mix-compare').innerHTML=mixStack('当前货盘', mix.sku_share)+mixStack('优化目标', mix.target_share);
  $('#mix-gaps').innerHTML=`<p>组合毛利 <strong>${mix.current_blended_margin_pct}%</strong> → 目标配比推演 <strong>${mix.target_blended_margin_pct}%</strong></p><p class="muted">独占均毛 ${mix.avg_margin_by_zone.EXCLUSIVE||0}% · 优质 ${mix.avg_margin_by_zone.ADVANTAGE||0}% · 同质 ${mix.avg_margin_by_zone.HOMOGENEOUS||0}%</p>`;
  $('#strategy-circles').innerHTML=os.strategy_circles.map(c=>`<div class="circle-row ${c.status.toLowerCase()}"><strong>${esc(c.label)}</strong><div class="bar"><i style="width:${c.score}%"></i></div><span>${c.score} · ${c.status}</span><small>${esc(c.note)}</small></div>`).join('');
  $('#os-actions').innerHTML=(os.recommended_actions||[]).map(a=>`<li>${esc(a)}</li>`).join('');
  $('#os-gaming').textContent=os.gaming_move||'';
  const a=os.advantage_audit||{};
  $('#advantage-audit').innerHTML=`<div class="metric-grid"><div class="metric"><small>在营 SKU+候选</small><strong>${a.live_skus||0}</strong></div><div class="metric"><small>伪优势/自嗨</small><strong>${a.fake_or_intoxicated||0}</strong></div><div class="metric"><small>靠谱缺口</small><strong>${a.reliability_gaps||0}</strong></div></div>`;
  const mg=os.management||{};
  if($('#os-cadence')) $('#os-cadence').textContent=mg.cadence||'';
  if($('#process-loop')) $('#process-loop').innerHTML=(mg.process_loop||[]).map(s=>`<li class="${s.active?'active':''}"><strong>${esc(s.no)} ${esc(s.label)}</strong><small>${esc(s.owner)} · ${esc(s.letter||s.talent)} ${esc(s.name||'')}</small></li>`).join('');
  if($('#os-goals')) $('#os-goals').innerHTML=(mg.goals||[]).map(g=>`<div class="circle-row ${g.status.toLowerCase()}"><strong>${esc(g.name)}</strong><div class="bar"><i style="width:${Math.min(100,Math.max(8,g.current))}%"></i></div><span>${g.current}${esc(g.unit)} / ${g.target}</span></div>`).join('');
  if($('#os-talent')) $('#os-talent').innerHTML=(mg.talent_value||[]).map(v=>`<div class="talent-card"><strong>${esc(v.letter)} ${esc(v.name)}</strong><p>${esc(v.meaning)}</p><small>${esc((v.agents||[]).join(' · '))}</small></div>`).join('');
  if($('#os-agenda')) $('#os-agenda').innerHTML=(mg.ceo_agenda||[]).map(x=>`<li>${esc(x)}</li>`).join('');
  const cb=os.crossborder||{};
  if($('#cb-fundamentals')) $('#cb-fundamentals').textContent=cb.customer_fundamentals||'';
  if($('#cb-sequence')) $('#cb-sequence').innerHTML=(cb.entry_sequence||[]).map(x=>`<li>${esc(x)}</li>`).join('');
  if($('#cb-channels')){
    const snap=cb.channel_mix_snapshot||[];
    const targets=cb.channel_mix||{};
    const cards=Object.entries(targets).map(([ch,pol])=>{
      const row=snap.find(s=>s.channel===ch);
      const share=row&&row.sku_share||{};
      return `<div class="talent-card"><strong>${esc(ch)}</strong><p>目标 独占${pol.exclusive_target_pct}% / 优质${pol.advantage_target_pct}% / 同质${pol.homogeneous_target_pct}%（同质警戒 ${pol.homogeneous_alert_pct}%）</p><small>当前 ${share.EXCLUSIVE||0}% / ${share.ADVANTAGE||0}% / ${share.HOMOGENEOUS||0}%</small></div>`;
    });
    $('#cb-channels').innerHTML=cards.join('')||'<div class="empty-state">暂无渠道配比</div>';
  }
}

function initListingPack(){
  const form=$('#listing-pack-form');
  if(!form) return;
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    await runListingPack(form.product_id.value);
  });
}

initNav(); initSelection(); initCandidateForm(); initDataHub(); initShopifyChannel(); initCommerce(); initListingPack();
const requestedView=new URLSearchParams(location.search).get('view') || location.hash.replace('#','');
if(requestedView){ const nav=document.querySelector(`[data-view="${requestedView}"]`); if(nav) nav.click(); }
Promise.all([loadDashboard(),loadProducts(),loadWorkforce(),loadOpportunities(),loadDataHub(),loadCommerce()]).catch(console.error);

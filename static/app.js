function $(sel){return document.querySelector(sel)}
function api(url, data){
  return fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(data)}).then(r=>r.json())
}
async function refresh(){
  const r = await fetch("/state"); const s = await r.json();
  $("#year").textContent = s.year;
  $("#people").textContent = s.counts.people;
  $("#living").textContent = s.counts.living;
  $("#unions").textContent = s.counts.unions;
  $("#families").textContent = s.counts.families;
  $("#version").textContent = s.version;
  // table
  const tb = $("#tbody"); tb.innerHTML = "";
  (s.people||[]).forEach(p=>{
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="px-3 py-2">${p.cedula||""}</td>
      <td class="px-3 py-2">${p.nombre||""}</td>
      <td class="px-3 py-2 text-center">${p.edad||0}</td>
      <td class="px-3 py-2 text-center">${p.vivo!==false?"✔":"✖"}</td>
      <td class="px-3 py-2 text-center">${p.pareja||""}</td>
      <td class="px-3 py-2 text-center">${(p.hijos||[]).length}</td>`;
    tb.appendChild(tr);
  });
  // tree
  const img = $("#treeImg");
  img.src = "/tree.svg?ts=" + encodeURIComponent(s.version);
}
refresh();
const es = new EventSource("/stream");
es.onmessage = (e)=>{
  try{
    const data = JSON.parse(e.data);
    $("#year").textContent = data.year;
    $("#people").textContent = data.counts.people;
    $("#living").textContent = data.counts.living;
    $("#unions").textContent = data.counts.unions;
    $("#families").textContent = data.counts.families;
    $("#version").textContent = data.version || "";
    // refresh tree on each change
    const img = $("#treeImg");
    img.src = "/tree.svg?ts=" + Date.now();
  }catch(err){ console.error(err); }
};
$("#familyForm").addEventListener("submit", async (ev)=>{
  ev.preventDefault();
  const name = ev.target.name.value.trim();
  if(!name) return;
  const res = await api("/families", {name});
  $("#familyOut").textContent = JSON.stringify(res,null,2);
  ev.target.reset();
});
$("#personForm").addEventListener("submit", async (ev)=>{
  ev.preventDefault();
  const f = ev.target;
  const intereses = f.intereses.value.trim()? f.intereses.value.split(",").map(s=>s.trim()).filter(Boolean) : [];
  const padres = f.padres.value.trim()? f.padres.value.split(",").map(s=>s.trim()).filter(Boolean) : [];
  const payload = {
    cedula: f.cedula.value.trim()||null,
    nombre: f.nombre.value.trim(),
    edad: Number(f.edad.value||0),
    genero: f.genero.value,
    provincia: f.provincia.value,
    estado_civil: f.estado_civil.value,
    intereses, padres, familia_id: f.familia_id.value.trim()||null
  };
  const res = await api("/people", payload);
  $("#personOut").textContent = JSON.stringify(res,null,2);
  f.reset();
  refresh();
});
$("#refreshTree").addEventListener("click", refresh);
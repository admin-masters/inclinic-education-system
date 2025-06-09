document.addEventListener('DOMContentLoaded', ()=>{
  const search = document.getElementById('searchBox');
  const rows   = document.querySelectorAll('#campTable tbody tr');
  search.addEventListener('keyup', ()=>{
    const q = search.value.toLowerCase();
    rows.forEach(r=>{
      const txt = r.querySelector('.camp').innerText.toLowerCase();
      r.style.display = txt.includes(q) ? '' : 'none';
    });
  });
});
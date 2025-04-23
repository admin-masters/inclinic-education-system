import { api } from '../api/client';
import {  useState } from 'react';
import { getCookie } from '../api/cookies';

export default function FieldRepBulk(){
  const [file,setFile]=useState<File|null>(null);

  const upload=async(e:React.FormEvent)=>{
    e.preventDefault();
    if(!file) return;
    const fd=new FormData(); fd.append('csv_file',file);
    await api.post('/admin/dashboard/bulk-fieldreps/',fd,{
      headers:{'X-CSRFToken':getCookie('csrftoken')}
    });
    alert('Uploaded');
  };

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Bulk Upload Field Reps</h1>
      <form onSubmit={upload}>
        <input type="file" accept=".csv" onChange={e=>setFile(e.target.files?.[0]||null)}/>
        <button className="bg-blue-600 text-white px-4 py-1 rounded ml-3">Upload</button>
      </form>
    </div>
  );
}
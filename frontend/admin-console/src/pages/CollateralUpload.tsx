import { useState } from 'react';
import { api } from '../api/client';

export default function CollateralUpload(){
  const [file,setFile]=useState<File|null>(null);
  const [title,setTitle]=useState('');
  const [type,setType]=useState<'pdf'|'video'>('pdf');
  const [url,setUrl]=useState('');

  const submit= async(e:React.FormEvent)=>{
    e.preventDefault();
    const fd=new FormData();
    fd.append('title',title);
    fd.append('type',type);
    if(type==='pdf' && file) fd.append('file',file);
    if(type==='video') fd.append('vimeo_url',url);
    await api.post('/api/collaterals/',fd);
    alert('Uploaded!');
  };

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Upload Collateral</h1>
      <form onSubmit={submit} className="space-y-4">
        <input value={title} onChange={e=>setTitle(e.target.value)}
               className="border p-1 w-full" placeholder="Title"/>
        <select value={type} onChange={e=>setType(e.target.value as any)}
                className="border p-1">
          <option value="pdf">PDF</option>
          <option value="video">Vimeo video</option>
        </select>
        {type==='pdf' ?
          <input type="file" onChange={e=>setFile(e.target.files?.[0]||null)}/> :
          <input value={url} onChange={e=>setUrl(e.target.value)}
                 className="border p-1 w-full" placeholder="Vimeo URL"/>
        }
        <button className="bg-blue-600 text-white px-4 py-2 rounded">Upload</button>
      </form>
    </div>
  );
}
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../api/client';
import { MetricCard } from '../components/MetricCard';

export default function CampaignDetail() {
  const { id } = useParams();
  const [info,setInfo] = useState<any>(null);

  useEffect(()=>{
    api.get(`/api/campaigns/${id}/summary/`).then(r=>setInfo(r.data));
  },[id]);

  if(!info) return <p className="p-6">Loading…</p>;

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-2">{info.name}</h1>
      <div className="grid grid-cols-3 gap-4 my-4">
        <MetricCard label="Shares" value={info.shares}/>
        <MetricCard label="PDF Impr." value={info.pdfs}/>
        <MetricCard label="Video Views" value={info.videos}/>
      </div>

      <h2 className="font-medium mb-2">Collaterals</h2>
      <ul className="list-disc ml-6">
        {info.collaterals.map((c:any)=>(
          <li key={c.id}>{c.title} ({c.type}) – Shares: {c.shares}</li>
        ))}
      </ul>
    </div>
  );
}
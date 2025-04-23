import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { MetricCard } from '../components/MetricCard';

type Stat = {
  campaign_id:number;
  campaign_name:string;
  shares:number;
  pdfs:number;
  videos:number;
};

export default function Dashboard() {
  const [stats,setStats] = useState<Stat[]>([]);

  useEffect(()=>{
    api.get('/admin/dashboard/json/')          // add this view (below)
       .then(r=>setStats(r.data))
       .catch(()=>alert('Error loading stats'));
  },[]);

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Campaign Metrics</h1>
      <div className="grid md:grid-cols-3 gap-4">
        {stats.map(s=>(
          <div key={s.campaign_id} className="border p-4 rounded shadow">
            <h3 className="font-medium mb-2">{s.campaign_name}</h3>
            <div className="grid grid-cols-3 gap-2">
              <MetricCard label="Shares" value={s.shares}/>
              <MetricCard label="PDFs"   value={s.pdfs}/>
              <MetricCard label="Videos" value={s.videos}/>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

type Campaign = { id:number; name:string; brand_name:string; status:string };

export default function CampaignList() {
  const [data,setData] = useState<Campaign[]>([]);
  const [q,setQ] = useState('');

  useEffect(()=>{ api.get('/api/campaigns/').then(r=>setData(r.data)); },[]);

  const rows = data.filter(c=>c.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Campaigns</h1>
      <input value={q} onChange={e=>setQ(e.target.value)}
             className="border p-1 mb-3" placeholder="Search…"/>
      <table className="w-full border">
        <thead className="bg-gray-100"><tr>
          <th className="p-2 text-left">Name</th><th>Brand</th><th>Status</th>
        </tr></thead>
        <tbody>
          {rows.map(c=>(
            <tr key={c.id} className="border-t">
              <td className="p-2">
                <Link className="text-blue-600" to={`/campaign/${c.id}`}>{c.name}</Link>
              </td>
              <td>{c.brand_name}</td>
              <td>{c.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { getCookie } from '../api/cookies';

interface Campaign {
  id: number;
  name: string;
  brand_campaign_id: string;
}

export default function FieldRepBulk(){
  const [file,setFile]=useState<File|null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Fetch campaigns when component mounts
    api.get('/campaign-management/api/campaigns/').then(response => {
      setCampaigns(response.data);
    }).catch(error => {
      console.error('Error fetching campaigns:', error);
    });
  }, []);

  const upload=async(e:React.FormEvent)=>{
    e.preventDefault();
    if(!file) return;
    setLoading(true);
    
    const fd=new FormData(); 
    fd.append('csv_file',file);
    if (selectedCampaign) {
      fd.append('campaign', selectedCampaign);
    }
    
    try {
      await api.post('/admin/dashboard/bulk-fieldreps/',fd,{
        headers:{'X-CSRFToken':getCookie('csrftoken')}
      });
      alert('Uploaded successfully!');
      setFile(null);
      setSelectedCampaign('');
      // Reset file input
      const fileInput = document.getElementById('csv-file') as HTMLInputElement;
      if (fileInput) fileInput.value = '';
    } catch (error: any) {
      console.error('Upload error:', error);
      alert(`Upload failed: ${error.response?.data?.message || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Bulk Upload Field Reps</h1>
      
      <form onSubmit={upload} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            CSV File (format: name,email,phone)
          </label>
          <input 
            id="csv-file"
            type="file" 
            accept=".csv" 
            onChange={e=>setFile(e.target.files?.[0]||null)}
            className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium mb-2">
            Campaign (Optional - Assign all field reps to this campaign)
          </label>
          <select 
            value={selectedCampaign}
            onChange={e=>setSelectedCampaign(e.target.value)}
            className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">No campaign assignment</option>
            {campaigns.map(campaign => (
              <option key={campaign.id} value={campaign.id}>
                {campaign.name} ({campaign.brand_campaign_id})
              </option>
            ))}
          </select>
        </div>
        
        <button 
          type="submit"
          disabled={loading || !file}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {loading ? 'Uploading...' : 'Upload'}
        </button>
      </form>
      
      <div className="mt-4 p-4 bg-yellow-50 rounded-md">
        <p className="text-sm text-yellow-800">
          <strong>Note:</strong> If you select a campaign, all field reps in this upload will be automatically assigned to that campaign and will appear in their field rep portal.
        </p>
      </div>
    </div>
  );
}
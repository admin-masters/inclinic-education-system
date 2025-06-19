import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import CampaignList from './pages/CampaignList';
import CampaignDetail from './pages/CampaignDetail';
import CollateralUpload from './pages/CollateralUpload';
import FieldRepBulk from './pages/FieldRepBulk';

export default function App() {
  return (
    <BrowserRouter basename="/console">
      <Navbar/>
      <Routes>
        <Route path="/dashboard" element={<Dashboard/>}/>
        <Route path="/campaigns" element={<CampaignList/>}/>
        <Route path="/campaign/:id" element={<CampaignDetail/>}/>
        <Route path="/collateral" element={<CollateralUpload/>}/>
        <Route path="/bulk-fieldreps" element={<FieldRepBulk/>}/>
        <Route path="*" element={<Dashboard/>}/>
      </Routes>
    </BrowserRouter>
  );
}
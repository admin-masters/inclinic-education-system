import { Link } from 'react-router-dom';
import { logout } from '../api/auth';
export default function Navbar() {
  return (
    <nav className="bg-slate-800 text-white px-4 py-2 flex gap-6">
      <Link to="/dashboard">Dashboard</Link>
      <Link to="/campaigns">Campaigns</Link>
      <Link to="/collateral">Collateral</Link>
      <Link to="/bulk-fieldreps">Bulk Upload Reps</Link>
      <button onClick={logout} className="ml-auto underline">Logout</button>
    </nav>
  );
}
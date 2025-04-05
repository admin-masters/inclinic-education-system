import { BrowserRouter as Router, Routes, Route } from "react-router-dom"
import Home from "./pages/Home"
import NotFound from "./pages/NotFound"
import LoginCallback from "./pages/LoginCallback"

import AdminDashboard from "./components/AdminDashboard"
import BrandManagerDashboard from "./components/BrandManagerDashboard"
import FieldRepDashboard from "./components/FieldRepDashboard"
import DoctorViewer from "./components/DoctorViewer"

import Navbar from "./components/Navbar"
import "./App.css"

function App() {
  return (
    <Router>
      <div className="app-container">
        <Navbar />
        <main className="content-container">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/auth/callback" element={<LoginCallback />} />

            {/* Admin route */}
            <Route path="/admin" element={<AdminDashboard />} />

            {/* Brand Manager route */}
            <Route path="/brand-manager" element={<BrandManagerDashboard />} />

            {/* Field Rep route */}
            <Route path="/field-rep" element={<FieldRepDashboard />} />

            {/* Doctor-facing page: PDF/Video viewer */}
            <Route path="/doctor/view/:shareId" element={<DoctorViewer />} />

            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App


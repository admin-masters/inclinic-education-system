"use client"
import { Link, useLocation } from "react-router-dom"

function Navbar() {
  const userRole = localStorage.getItem("userRole")
  const location = useLocation()

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <div className="navbar-logo">
          <Link to="/">InClinic</Link>
        </div>
        <div className="navbar-links">
          <Link to="/" className={location.pathname === "/" ? "active" : ""}>
            Home
          </Link>

          {userRole === "ADMIN" && (
            <Link to="/admin" className={location.pathname === "/admin" ? "active" : ""}>
              Admin Dashboard
            </Link>
          )}

          {userRole === "BRAND_MANAGER" && (
            <Link to="/brand-manager" className={location.pathname === "/brand-manager" ? "active" : ""}>
              Brand Manager
            </Link>
          )}

          {userRole === "FIELD_REP" && (
            <Link to="/field-rep" className={location.pathname === "/field-rep" ? "active" : ""}>
              Field Rep
            </Link>
          )}
        </div>

        <div className="navbar-auth">
          {userRole ? (
            <button
              className="btn btn-secondary"
              onClick={() => {
                localStorage.removeItem("userRole")
                window.location.href = "/"
              }}
            >
              Logout
            </button>
          ) : (
            <button className="btn btn-primary">Login</button>
          )}
        </div>
      </div>

      <style jsx>{`
        .navbar {
          background-color: var(--background);
          border-bottom: 1px solid var(--border);
          padding: 0.75rem 1.5rem;
        }
        
        .navbar-container {
          display: flex;
          align-items: center;
          justify-content: space-between;
          max-width: 1200px;
          margin: 0 auto;
        }
        
        .navbar-logo a {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--primary);
          text-decoration: none;
        }
        
        .navbar-links {
          display: flex;
          gap: 1.5rem;
        }
        
        .navbar-links a {
          color: var(--text-secondary);
          text-decoration: none;
          font-weight: 500;
          padding: 0.5rem 0;
          position: relative;
        }
        
        .navbar-links a:hover {
          color: var(--text-primary);
        }
        
        .navbar-links a.active {
          color: var(--primary);
        }
        
        .navbar-links a.active:after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 2px;
          background-color: var(--primary);
        }
      `}</style>
    </nav>
  )
}

export default Navbar


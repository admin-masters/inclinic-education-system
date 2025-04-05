"use client"

import { useEffect, useState } from "react"
import { useSearchParams, useNavigate } from "react-router-dom"

function LoginCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState("Processing login...")

  useEffect(() => {
    // Suppose the Django backend redirects here with ?userRole=FIELD_REP or brand manager or admin
    const userRole = searchParams.get("userRole")

    if (userRole) {
      localStorage.setItem("userRole", userRole)
      setStatus("Login successful! Redirecting...")

      // Redirect based on role
      setTimeout(() => {
        switch (userRole) {
          case "ADMIN":
            navigate("/admin")
            break
          case "BRAND_MANAGER":
            navigate("/brand-manager")
            break
          case "FIELD_REP":
            navigate("/field-rep")
            break
          default:
            navigate("/")
        }
      }, 1500)
    } else {
      setStatus("Login failed. Missing user role information.")
      setTimeout(() => navigate("/"), 2000)
    }
  }, [searchParams, navigate])

  return (
    <div className="login-callback">
      <div className="card">
        <div className="loader"></div>
        <h2>{status}</h2>
      </div>

      <style jsx>{`
        .login-callback {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 60vh;
        }
        
        .card {
          text-align: center;
          padding: 2rem;
          max-width: 400px;
        }
        
        .loader {
          border: 4px solid rgba(0, 0, 0, 0.1);
          border-radius: 50%;
          border-top: 4px solid var(--primary);
          width: 40px;
          height: 40px;
          animation: spin 1s linear infinite;
          margin: 0 auto 1.5rem;
        }
        
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

export default LoginCallback


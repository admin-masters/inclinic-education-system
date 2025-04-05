"use client"
import { Link } from "react-router-dom"

function NotFound() {
  return (
    <div className="not-found">
      <h1>404</h1>
      <h2>Page Not Found</h2>
      <p>The page you are looking for doesn't exist or has been moved.</p>
      <Link to="/" className="btn btn-primary">
        Go Home
      </Link>

      <style jsx>{`
        .not-found {
          text-align: center;
          padding: 4rem 1rem;
          max-width: 500px;
          margin: 0 auto;
        }
        
        .not-found h1 {
          font-size: 6rem;
          color: var(--primary);
          margin-bottom: 0;
        }
        
        .not-found h2 {
          margin-bottom: 1rem;
        }
        
        .not-found p {
          margin-bottom: 2rem;
          color: var(--text-secondary);
        }
      `}</style>
    </div>
  )
}

export default NotFound


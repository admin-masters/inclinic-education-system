"use client"

function Home() {
  return (
    <div className="home-container">
      <div className="hero-section">
        <h1>Welcome to the In-Clinic Education System</h1>
        <p className="hero-description">
          A comprehensive platform for sharing educational content with healthcare professionals.
        </p>
      </div>

      <div className="features-section">
        <div className="card">
          <h2>For Doctors</h2>
          <p>Access educational materials shared by field representatives directly through secure links.</p>
        </div>

        <div className="card">
          <h2>For Field Representatives</h2>
          <p>Share campaign content with doctors easily and track engagement.</p>
        </div>

        <div className="card">
          <h2>For Brand Managers</h2>
          <p>Create and manage campaigns, monitor field rep activities and content performance.</p>
        </div>

        <div className="card">
          <h2>For Administrators</h2>
          <p>Oversee the entire platform, manage users, and analyze system-wide metrics.</p>
        </div>
      </div>

      <style jsx>{`
        .home-container {
          max-width: 1200px;
          margin: 0 auto;
        }
        
        .hero-section {
          text-align: center;
          padding: 3rem 1rem;
          margin-bottom: 2rem;
        }
        
        .hero-description {
          font-size: 1.25rem;
          color: var(--text-secondary);
          max-width: 600px;
          margin: 0 auto;
        }
        
        .features-section {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
          gap: 1.5rem;
        }
        
        .features-section .card {
          height: 100%;
        }
      `}</style>
    </div>
  )
}

export default Home


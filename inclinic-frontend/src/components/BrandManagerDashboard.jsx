"use client"

import { useEffect, useState } from "react"
import axiosInstance from "../api/axiosInstance"

function BrandManagerDashboard() {
  const [myCampaigns, setMyCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCampaign, setSelectedCampaign] = useState(null)
  const [campaignDetails, setCampaignDetails] = useState(null)
  const [detailsLoading, setDetailsLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    axiosInstance
      .get("/brand-manager/api/my-campaigns")
      .then((res) => {
        setMyCampaigns(res.data)
        setLoading(false)
      })
      .catch((err) => {
        console.error("Error:", err)
        setError("Failed to load campaigns. Please try again later.")
        setLoading(false)
      })

    // Mock data for demonstration
    setTimeout(() => {
      setMyCampaigns([
        {
          campaign_id: 1,
          campaign_name: "Diabetes Awareness 2023",
          status: "Active",
          created_at: "2023-05-15",
          content_count: 5,
          field_reps: 12,
          views: 156,
          shares: 48,
        },
        {
          campaign_id: 2,
          campaign_name: "Heart Health Initiative",
          status: "Active",
          created_at: "2023-06-22",
          content_count: 8,
          field_reps: 15,
          views: 203,
          shares: 67,
        },
        {
          campaign_id: 3,
          campaign_name: "Respiratory Care Program",
          status: "Draft",
          created_at: "2023-07-10",
          content_count: 3,
          field_reps: 0,
          views: 0,
          shares: 0,
        },
      ])
      setLoading(false)
    }, 1000)
  }, [])

  // Function to handle viewing campaign details
  const handleViewCampaign = (campaign) => {
    setSelectedCampaign(campaign)
    setDetailsLoading(true)

    // Simulate API call to get campaign details
    setTimeout(() => {
      // Mock detailed campaign data
      setCampaignDetails({
        ...campaign,
        description: "This campaign focuses on raising awareness about diabetes prevention and management.",
        target_audience: "Healthcare professionals specializing in endocrinology and primary care",
        start_date: "2023-05-15",
        end_date: "2023-12-31",
        budget: "$25,000",
        contents: [
          { id: 1, title: "Understanding Diabetes Types", type: "PDF", views: 45, shares: 12 },
          { id: 2, title: "Managing Blood Sugar Levels", type: "PDF", views: 38, shares: 15 },
          { id: 3, title: "Patient Testimonial: Living with Diabetes", type: "VIDEO", views: 73, shares: 21 },
        ],
        assigned_reps: [
          { id: 1, name: "John Smith", region: "Northeast", shares: 18 },
          { id: 2, name: "Sarah Johnson", region: "Midwest", shares: 15 },
          { id: 3, name: "Michael Brown", region: "West", shares: 15 },
        ],
      })
      setDetailsLoading(false)
    }, 800)
  }

  // Function to close campaign details
  const closeCampaignDetails = () => {
    setSelectedCampaign(null)
    setCampaignDetails(null)
  }

  return (
    <div className="brand-manager-dashboard">
      <div className="dashboard-header">
        <h1>Brand Manager Dashboard</h1>
        <button className="btn btn-primary">Create New Campaign</button>
      </div>

      {selectedCampaign && campaignDetails ? (
        <div className="campaign-details-view">
          <div className="details-header">
            <div>
              <button className="btn btn-secondary" onClick={closeCampaignDetails}>
                ← Back to Campaigns
              </button>
            </div>
            <h2>{campaignDetails.campaign_name}</h2>
            <span className={`status-badge ${campaignDetails.status.toLowerCase()}`}>{campaignDetails.status}</span>
          </div>

          {detailsLoading ? (
            <div className="loading-state">Loading campaign details...</div>
          ) : (
            <div className="details-content">
              <div className="details-grid">
                <div className="card">
                  <h3>Campaign Overview</h3>
                  <div className="detail-item">
                    <span className="detail-label">Description:</span>
                    <span className="detail-value">{campaignDetails.description}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Target Audience:</span>
                    <span className="detail-value">{campaignDetails.target_audience}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Duration:</span>
                    <span className="detail-value">
                      {campaignDetails.start_date} to {campaignDetails.end_date}
                    </span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Budget:</span>
                    <span className="detail-value">{campaignDetails.budget}</span>
                  </div>
                </div>

                <div className="card">
                  <h3>Performance Metrics</h3>
                  <div className="stats-grid">
                    <div className="stat-card">
                      <div className="stat-value">{campaignDetails.content_count}</div>
                      <div className="stat-label">Content Items</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{campaignDetails.field_reps}</div>
                      <div className="stat-label">Field Reps</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{campaignDetails.views}</div>
                      <div className="stat-label">Total Views</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-value">{campaignDetails.shares}</div>
                      <div className="stat-label">Total Shares</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="details-tables">
                <div className="card">
                  <h3>Campaign Content</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Type</th>
                        <th>Views</th>
                        <th>Shares</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaignDetails.contents.map((content) => (
                        <tr key={content.id}>
                          <td>{content.title}</td>
                          <td>
                            <span className="content-type-badge">{content.type}</span>
                          </td>
                          <td>{content.views}</td>
                          <td>{content.shares}</td>
                          <td>
                            <button className="btn-icon">Preview</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="card">
                  <h3>Assigned Field Representatives</h3>
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Region</th>
                        <th>Shares</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaignDetails.assigned_reps.map((rep) => (
                        <tr key={rep.id}>
                          <td>{rep.name}</td>
                          <td>{rep.region}</td>
                          <td>{rep.shares}</td>
                          <td>
                            <button className="btn-icon">Contact</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="dashboard-content">
          <div className="campaigns-overview card">
            <h2>Campaign Overview</h2>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{myCampaigns.length}</div>
                <div className="stat-label">Total Campaigns</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{myCampaigns.filter((c) => c.status === "Active").length}</div>
                <div className="stat-label">Active Campaigns</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{myCampaigns.reduce((total, campaign) => total + campaign.views, 0)}</div>
                <div className="stat-label">Total Views</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{myCampaigns.reduce((total, campaign) => total + campaign.shares, 0)}</div>
                <div className="stat-label">Total Shares</div>
              </div>
            </div>
          </div>

          <div className="campaigns-section">
            <div className="card">
              <div className="card-header">
                <h2>My Campaigns</h2>
                <div className="search-filter">
                  <input type="text" placeholder="Search campaigns..." />
                </div>
              </div>

              {loading ? (
                <div className="loading-state">Loading campaigns...</div>
              ) : error ? (
                <div className="error-state">{error}</div>
              ) : (
                <div className="campaigns-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Campaign Name</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Content</th>
                        <th>Field Reps</th>
                        <th>Views</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {myCampaigns.map((campaign) => (
                        <tr key={campaign.campaign_id}>
                          <td>{campaign.campaign_name}</td>
                          <td>
                            <span className={`status-badge ${campaign.status.toLowerCase()}`}>{campaign.status}</span>
                          </td>
                          <td>{campaign.created_at}</td>
                          <td>{campaign.content_count} items</td>
                          <td>{campaign.field_reps} reps</td>
                          <td>{campaign.views}</td>
                          <td>
                            <div className="action-buttons">
                              <button className="btn-icon">Edit</button>
                              <button className="btn-icon" onClick={() => handleViewCampaign(campaign)}>
                                View
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .brand-manager-dashboard {
          max-width: 1200px;
          margin: 0 auto;
        }
        
        .dashboard-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 1rem;
          margin-top: 1rem;
        }
        
        .stat-card {
          background-color: var(--card-bg);
          border-radius: 0.5rem;
          padding: 1.5rem;
          text-align: center;
        }
        
        .stat-value {
          font-size: 2rem;
          font-weight: 700;
          color: var(--primary);
          margin-bottom: 0.5rem;
        }
        
        .stat-label {
          color: var(--text-secondary);
          font-size: 0.875rem;
        }
        
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        
        .campaigns-table {
          overflow-x: auto;
        }
        
        table {
          width: 100%;
          border-collapse: collapse;
        }
        
        th, td {
          padding: 0.75rem 1rem;
          text-align: left;
          border-bottom: 1px solid var(--border);
        }
        
        th {
          font-weight: 500;
          color: var(--text-secondary);
        }
        
        .status-badge {
          display: inline-block;
          padding: 0.25rem 0.5rem;
          border-radius: 9999px;
          font-size: 0.75rem;
          font-weight: 500;
        }
        
        .status-badge.active {
          background-color: rgba(16, 185, 129, 0.1);
          color: var(--success);
        }
        
        .status-badge.inactive {
          background-color: rgba(239, 68, 68, 0.1);
          color: var(--error);
        }
        
        .status-badge.draft {
          background-color: rgba(245, 158, 11, 0.1);
          color: var(--warning);
        }
        
        .action-buttons {
          display: flex;
          gap: 0.5rem;
        }
        
        .btn-icon {
          padding: 0.25rem 0.5rem;
          background-color: var(--secondary);
          border: 1px solid var(--border);
          border-radius: 0.25rem;
          font-size: 0.75rem;
          cursor: pointer;
        }
        
        .btn-icon:hover {
          background-color: var(--border);
        }
        
        .loading-state, .error-state {
          padding: 2rem;
          text-align: center;
          color: var(--text-secondary);
        }
        
        .error-state {
          color: var(--error);
        }
        
        /* Campaign Details Styles */
        .campaign-details-view {
          margin-top: 1rem;
        }
        
        .details-header {
          margin-bottom: 1.5rem;
        }
        
        .details-header h2 {
          margin: 1rem 0 0.5rem;
        }
        
        .details-content {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        
        .details-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1.5rem;
        }
        
        @media (max-width: 768px) {
          .details-grid {
            grid-template-columns: 1fr;
          }
        }
        
        .detail-item {
          margin-bottom: 0.75rem;
          display: flex;
          flex-direction: column;
        }
        
        .detail-label {
          font-weight: 500;
          color: var(--text-secondary);
          font-size: 0.875rem;
        }
        
        .detail-value {
          margin-top: 0.25rem;
        }
        
        .details-tables {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        
        .content-type-badge {
          display: inline-block;
          padding: 0.25rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 500;
          background-color: var(--primary);
          color: white;
        }
        
        .card h3 {
          margin-bottom: 1rem;
          font-size: 1.25rem;
        }
      `}</style>
    </div>
  )
}

export default BrandManagerDashboard


"use client"

import { useEffect, useState } from "react"
import axiosInstance from "../api/axiosInstance"

function AdminDashboard() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState("campaigns")

  useEffect(() => {
    // Example: fetch all campaigns from Django
    setLoading(true)
    axiosInstance
      .get("/admin/api/campaigns")
      .then((response) => {
        setCampaigns(response.data)
        setLoading(false)
      })
      .catch((error) => {
        console.error("Error fetching campaigns:", error)
        setError("Failed to load campaigns. Please try again later.")
        setLoading(false)
      })

    // For demonstration purposes only - in production, remove this mock data
    // and use the actual API response
    setTimeout(() => {
      setCampaigns([
        {
          campaign_id: 1,
          campaign_name: "Diabetes Awareness 2023",
          status: "Active",
          content_count: 5,
          field_reps: 12,
        },
        {
          campaign_id: 2,
          campaign_name: "Heart Health Initiative",
          status: "Active",
          content_count: 8,
          field_reps: 15,
        },
        {
          campaign_id: 3,
          campaign_name: "Respiratory Care Program",
          status: "Inactive",
          content_count: 3,
          field_reps: 7,
        },
        { campaign_id: 4, campaign_name: "Mental Health Awareness", status: "Draft", content_count: 0, field_reps: 0 },
      ])
      setLoading(false)
    }, 1000)
  }, [])

  return (
    <div className="admin-dashboard">
      <div className="dashboard-header">
        <h1>Admin Dashboard</h1>
        <button className="btn btn-primary">Create New Campaign</button>
      </div>

      <div className="dashboard-tabs">
        <button
          className={`tab-button ${activeTab === "campaigns" ? "active" : ""}`}
          onClick={() => setActiveTab("campaigns")}
        >
          Campaigns
        </button>
        <button className={`tab-button ${activeTab === "users" ? "active" : ""}`} onClick={() => setActiveTab("users")}>
          Users
        </button>
        <button
          className={`tab-button ${activeTab === "analytics" ? "active" : ""}`}
          onClick={() => setActiveTab("analytics")}
        >
          Analytics
        </button>
      </div>

      <div className="dashboard-content">
        {activeTab === "campaigns" && (
          <div className="campaigns-section">
            <div className="card">
              <div className="card-header">
                <h2>All Campaigns</h2>
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
                        <th>Content</th>
                        <th>Field Reps</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Use the campaigns state instead of mockCampaigns */}
                      {campaigns.map((campaign) => (
                        <tr key={campaign.campaign_id}>
                          <td>{campaign.campaign_name}</td>
                          <td>
                            <span className={`status-badge ${campaign.status.toLowerCase()}`}>{campaign.status}</span>
                          </td>
                          <td>{campaign.content_count} items</td>
                          <td>{campaign.field_reps} reps</td>
                          <td>
                            <div className="action-buttons">
                              <button className="btn-icon">Edit</button>
                              <button className="btn-icon">View</button>
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
        )}

        {activeTab === "users" && (
          <div className="users-section">
            <div className="card">
              <h2>User Management</h2>
              <p>Manage brand managers and field representatives.</p>
              {/* User management UI would go here */}
            </div>
          </div>
        )}

        {activeTab === "analytics" && (
          <div className="analytics-section">
            <div className="card">
              <h2>System Analytics</h2>
              <p>View system-wide metrics and performance data.</p>
              {/* Analytics UI would go here */}
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        .admin-dashboard {
          max-width: 1200px;
          margin: 0 auto;
        }
        
        .dashboard-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        
        .dashboard-tabs {
          display: flex;
          border-bottom: 1px solid var(--border);
          margin-bottom: 1.5rem;
        }
        
        .tab-button {
          padding: 0.75rem 1.5rem;
          background: none;
          border: none;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          position: relative;
        }
        
        .tab-button:hover {
          color: var(--text-primary);
        }
        
        .tab-button.active {
          color: var(--primary);
        }
        
        .tab-button.active:after {
          content: '';
          position: absolute;
          bottom: -1px;
          left: 0;
          right: 0;
          height: 2px;
          background-color: var(--primary);
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
      `}</style>
    </div>
  )
}

export default AdminDashboard


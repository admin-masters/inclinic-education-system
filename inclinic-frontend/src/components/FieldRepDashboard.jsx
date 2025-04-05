"use client";

import React, { useState, useEffect } from "react";
import {
  getCampaigns,
  getCampaignContents,
  createShare,
} from "../api/apiService";

const FieldRepDashboard = () => {
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [contents, setContents] = useState([]);
  const [doctorPhone, setDoctorPhone] = useState("");
  const [selectedContent, setSelectedContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    setLoading(true);
    try {
      const response = await getCampaigns();
      setCampaigns(response.data);
    } catch (error) {
      console.error("Error loading campaigns:", error);
      setMessage("Failed to load campaigns.");
    } finally {
      setLoading(false);
    }
  };

  const handleCampaignSelect = async (campaign) => {
    setSelectedCampaign(campaign);
    setMessage("");

    try {
      const response = await getCampaignContents(campaign.id);
      setContents(response.data);
    } catch (error) {
      console.error("Error loading contents:", error);
      setMessage("Failed to load campaign contents.");
    }
  };

  const handleShareContent = async (e) => {
    e.preventDefault();

    if (!selectedContent || !doctorPhone) {
      setMessage("Please select content and enter doctor phone number.");
      return;
    }

    setLoading(true);
    try {
      await createShare({
        campaign: selectedCampaign.id,
        content: selectedContent,
        doctor_phone: doctorPhone,
      });

      setMessage("Content shared successfully!");
      setDoctorPhone("");
      setSelectedContent(null);
    } catch (error) {
      console.error("Error sharing content:", error);
      setMessage("Failed to share content.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="field-rep-dashboard">
      <h2>Field Representative Dashboard</h2>

      {message && <div className="message">{message}</div>}

      <h3>Available Campaigns</h3>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <div className="campaign-list">
          {campaigns.length > 0 ? (
            campaigns.map((campaign) => (
              <div
                key={campaign.id}
                className={`campaign-item ${
                  selectedCampaign && selectedCampaign.id === campaign.id
                    ? "selected"
                    : ""
                }`}
                onClick={() => handleCampaignSelect(campaign)}
              >
                <h4>{campaign.campaign_name}</h4>
                <p>Therapy Area: {campaign.therapy_area}</p>
              </div>
            ))
          ) : (
            <p>No active campaigns found.</p>
          )}
        </div>
      )}

      {selectedCampaign && (
        <div className="share-content-section">
          <h3>Share Content - {selectedCampaign.campaign_name}</h3>

          <form onSubmit={handleShareContent}>
            <div className="form-group">
              <label htmlFor="doctorPhone">Doctor's Phone Number:</label>
              <input
                type="text"
                id="doctorPhone"
                value={doctorPhone}
                onChange={(e) => setDoctorPhone(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label>Select Content to Share:</label>
              <div className="content-list">
                {contents.length > 0 ? (
                  contents.map((content) => (
                    <div
                      key={content.id}
                      className={`content-item ${
                        selectedContent === content.id ? "selected" : ""
                      }`}
                      onClick={() => setSelectedContent(content.id)}
                    >
                      <h5>{content.content_title}</h5>
                      <p>Type: {content.content_type}</p>
                    </div>
                  ))
                ) : (
                  <p>No content available for this campaign.</p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !selectedContent || !doctorPhone}
            >
              {loading ? "Sharing..." : "Share with Doctor"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};

export default FieldRepDashboard;

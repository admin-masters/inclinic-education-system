"use client";

import React, { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { getDoctorContent } from "../api/apiService";

const DoctorViewer = () => {
  const { shareId } = useParams();
  const [contentData, setContentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchContent = async () => {
      try {
        const response = await getDoctorContent(shareId);
        setContentData(response.data);
        setLoading(false);
      } catch (err) {
        console.error("Error loading content:", err);
        setError(
          "Failed to load the requested content. The link may be invalid or expired."
        );
        setLoading(false);
      }
    };

    fetchContent();
  }, [shareId]);

  if (loading) {
    return (
      <div className="doctor-viewer loading">
        <div className="loader">Loading content...</div>
      </div>
    );
  }

  if (error || !contentData) {
    return (
      <div className="doctor-viewer error">
        <h2>Content Not Available</h2>
        <p>{error || "The requested content could not be found."}</p>
      </div>
    );
  }

  const { content } = contentData;

  return (
    <div className="doctor-viewer">
      <div className="content-header">
        <h2>{content.content_title}</h2>
        <p>Campaign: {contentData.campaign.campaign_name}</p>
      </div>

      <div className="content-display">
        {content.content_type === "PDF" && (
          <div className="pdf-viewer">
            <iframe
              src={content.file_path}
              title={content.content_title}
              width="100%"
              height="600px"
              frameBorder="0"
            />
          </div>
        )}

        {content.content_type === "VIDEO" && (
          <div className="video-viewer">
            <iframe
              src={content.vimeo_url}
              title={content.content_title}
              width="100%"
              height="400px"
              frameBorder="0"
              allow="autoplay; fullscreen; picture-in-picture"
              allowFullScreen
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default DoctorViewer;

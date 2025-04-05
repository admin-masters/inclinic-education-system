import axiosInstance from "./axiosInstance";

// Authentication
export const checkAuth = async () => {
  return axiosInstance.get("/auth/check/");
};

// Campaigns
export const getCampaigns = async () => {
  return axiosInstance.get("/campaigns/");
};

export const getCampaign = async (id) => {
  return axiosInstance.get(`/campaigns/${id}/`);
};

export const createCampaign = async (campaignData) => {
  return axiosInstance.post("/campaigns/", campaignData);
};

export const updateCampaign = async (id, campaignData) => {
  return axiosInstance.put(`/campaigns/${id}/`, campaignData);
};

export const archiveCampaign = async (id) => {
  return axiosInstance.patch(`/campaigns/${id}/`, { status: "ARCHIVED" });
};

// Campaign Content
export const getCampaignContents = async (campaignId) => {
  return axiosInstance.get("/contents/", {
    params: { campaign_id: campaignId },
  });
};

export const createContent = async (contentData) => {
  return axiosInstance.post("/contents/", contentData);
};

// Doctor Shares
export const getShares = async () => {
  return axiosInstance.get("/shares/");
};

export const createShare = async (shareData) => {
  return axiosInstance.post("/shares/", shareData);
};

export const getDoctorContent = async (shareId) => {
  return axiosInstance.get(`/doctor/content/${shareId}/`);
};

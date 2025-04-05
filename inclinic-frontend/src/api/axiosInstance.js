import axios from "axios";

const axiosInstance = axios.create({
  baseURL: "http://127.0.0.1:8000/api",
  withCredentials: true, // if using cookies/session from Django
});

export default axiosInstance;

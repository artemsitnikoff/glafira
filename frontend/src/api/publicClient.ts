import axios from 'axios';

// Лёгкий axios без auth-интерцептора — для публичных страниц (SchedulePage, SurveyPublicPage).
// НЕ использовать для защищённых эндпоинтов.
export const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

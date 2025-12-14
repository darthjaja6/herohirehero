export const config = {
  baseUrl: process.env.REACT_APP_BASE_URL || 'http://localhost:3000',
  env: process.env.REACT_APP_ENV || 'development',
  isDev: process.env.REACT_APP_ENV !== 'production',
  isProd: process.env.REACT_APP_ENV === 'production',
};

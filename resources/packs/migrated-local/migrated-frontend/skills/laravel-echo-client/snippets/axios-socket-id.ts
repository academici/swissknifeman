// Source: anonymized production project
//
// Forwarding X-Socket-ID in every outgoing request. Backend via
// broadcast(...)->toOthers() excludes the current socket from broadcasting, so
// initiator does not receive its own event again (optimistic UI + echo).
//
// Placed in bootstrap front, next to the setting axios (CSRF, withCredentials).

import axios from "axios";

window.axios = axios;
window.axios.defaults.headers.common["X-Requested-With"] = "XMLHttpRequest";

const csrf = document.head?.querySelector<HTMLMetaElement>("meta[name='csrf-token']");
if (csrf?.content) {
  window.axios.defaults.headers.common["X-CSRF-TOKEN"] = csrf.content;
  window.axios.defaults.withCredentials = true;
}

// For each request - current socketId (if Echo connected).
window.axios.interceptors.request.use((config) => {
  const socketId = window.echo?.socketId?.();

  if (socketId) {
    config.headers = config.headers ?? {};
    config.headers["X-Socket-ID"] = socketId;
  }

  return config;
});

// For Inertia-visits (router.visit / useForm) the same header is sent
// via option headers, because they are passing by axios-interceptor:
//
//   const socketId = window.echo?.socketId?.();
//   router.post(route, data, {
//     headers: socketId ? { "X-Socket-ID": socketId } : {},
//   });

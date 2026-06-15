// Source: anonymized production project
//
// Проброс X-Socket-ID в каждый исходящий запрос. Backend через
// broadcast(...)->toOthers() исключает текущий сокет из рассылки, поэтому
// инициатор не получает собственное событие повторно (оптимистичный UI + echo).
//
// Кладётся в bootstrap фронта, рядом с настройкой axios (CSRF, withCredentials).

import axios from "axios";

window.axios = axios;
window.axios.defaults.headers.common["X-Requested-With"] = "XMLHttpRequest";

const csrf = document.head?.querySelector<HTMLMetaElement>("meta[name='csrf-token']");
if (csrf?.content) {
  window.axios.defaults.headers.common["X-CSRF-TOKEN"] = csrf.content;
  window.axios.defaults.withCredentials = true;
}

// На каждый запрос — текущий socketId (если Echo подключён).
window.axios.interceptors.request.use((config) => {
  const socketId = window.echo?.socketId?.();

  if (socketId) {
    config.headers = config.headers ?? {};
    config.headers["X-Socket-ID"] = socketId;
  }

  return config;
});

// Для Inertia-визитов (router.visit / useForm) тот же заголовок передаётся
// через опцию headers, т.к. они идут мимо axios-интерсептора:
//
//   const socketId = window.echo?.socketId?.();
//   router.post(route, data, {
//     headers: socketId ? { "X-Socket-ID": socketId } : {},
//   });

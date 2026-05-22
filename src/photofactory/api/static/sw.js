self.addEventListener("push", (event) => {
  let payload = { title: "Photofactory", body: "Новое уведомление" };
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (_err) {
      payload = { title: "Photofactory", body: event.data.text() };
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "Photofactory", {
      body: payload.body || "Новое уведомление",
      data: payload,
      icon: "/favicon.ico",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/pwa/test"));
});

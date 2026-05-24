self.addEventListener("push", (event) => {
  let payload = { title: "Bildboard Yauza", body: "Новое уведомление" };
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (_err) {
      payload = { title: "Bildboard Yauza", body: event.data.text() };
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "Bildboard Yauza", {
      body: payload.body || "Новое уведомление",
      data: payload,
      icon: "/favicon.ico",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const targetPath = typeof data.url === "string" && data.url.trim() ? data.url : "/bild";
  event.waitUntil((async () => {
    const allClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of allClients) {
      if ("focus" in client && client.url.includes(targetPath)) {
        await client.focus();
        return;
      }
    }
    await clients.openWindow(targetPath);
  })());
});

import { useState, useEffect, useRef } from "react";

export function useSSE(url) {
  const [events, setEvents] = useState([]);
  const esRef = useRef(null);

  useEffect(() => {
    let retryTimeout;

    function connect() {
      const es = new EventSource(url);
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setEvents((prev) => [data, ...prev].slice(0, 100));
        } catch (_) {}
      };

      es.onerror = () => {
        es.close();
        retryTimeout = setTimeout(connect, 2000);
      };
    }

    connect();
    return () => {
      clearTimeout(retryTimeout);
      esRef.current?.close();
    };
  }, [url]);

  return events;
}

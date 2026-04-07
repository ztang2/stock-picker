import { useState, useEffect } from "react";
import type { TimeOfDay } from "../lib/types";

export function useTimeOfDay(): TimeOfDay {
  const [tod, setTod] = useState<TimeOfDay>(getTimeOfDay);

  useEffect(() => {
    const interval = setInterval(() => setTod(getTimeOfDay()), 60_000);
    return () => clearInterval(interval);
  }, []);

  return tod;
}

function getTimeOfDay(): TimeOfDay {
  const hour = new Date().getHours();
  if (hour < 11) return "morning";
  if (hour < 14) return "midday";
  return "evening";
}

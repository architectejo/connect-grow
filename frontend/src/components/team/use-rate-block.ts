import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Désactive une action après un 429. Avec un `Retry-After` lisible, elle se réactive à l'échéance ;
 * sinon elle le reste jusqu'à la fermeture de la fenêtre.
 */
export function useRateBlock(): [boolean, (seconds?: number) => void] {
  const [blocked, setBlocked] = useState(false);
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const block = useCallback((seconds?: number) => {
    setBlocked(true);
    window.clearTimeout(timer.current);
    if (seconds !== undefined) timer.current = window.setTimeout(() => setBlocked(false), seconds * 1000);
  }, []);
  return [blocked, block];
}

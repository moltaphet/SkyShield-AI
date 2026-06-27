"use client";

import { useEffect, useState } from "react";

interface Star {
  top: string;
  left: string;
  size: number;
  dur: string;
  delay: string;
}

interface Cloud {
  top: string;
  size: number;
  dur: string;
  delay: string;
  opacity: number;
}

/**
 * Animated cyberpunk-sky background: twinkling stars + slow-drifting blue
 * clouds. Generated on the client after mount so the random layout never
 * triggers an SSR/CSR hydration mismatch.
 */
export function Starfield() {
  const [stars, setStars] = useState<Star[]>([]);
  const [clouds, setClouds] = useState<Cloud[]>([]);

  useEffect(() => {
    const nextStars: Star[] = Array.from({ length: 120 }, () => ({
      top: `${Math.random() * 100}%`,
      left: `${Math.random() * 100}%`,
      size: Math.random() * 2 + 1,
      dur: `${Math.random() * 4 + 2.5}s`,
      delay: `${Math.random() * 5}s`,
    }));
    const nextClouds: Cloud[] = Array.from({ length: 7 }, () => ({
      top: `${Math.random() * 90}%`,
      size: Math.random() * 320 + 180,
      dur: `${Math.random() * 40 + 50}s`,
      delay: `${-Math.random() * 60}s`,
      opacity: Math.random() * 0.5 + 0.3,
    }));
    setStars(nextStars);
    setClouds(nextClouds);
  }, []);

  return (
    <div className="starfield" aria-hidden>
      {clouds.map((c, i) => (
        <div
          key={`c${i}`}
          className="cloud"
          style={{
            top: c.top,
            width: c.size,
            height: c.size * 0.55,
            animationDuration: c.dur,
            animationDelay: c.delay,
            opacity: c.opacity,
          }}
        />
      ))}
      {stars.map((s, i) => (
        <div
          key={`s${i}`}
          className="star"
          style={{
            top: s.top,
            left: s.left,
            width: s.size,
            height: s.size,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            ["--dur" as any]: s.dur,
            animationDelay: s.delay,
          }}
        />
      ))}
    </div>
  );
}

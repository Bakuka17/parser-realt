import React from 'react';
import {
  AbsoluteFill,
  Img,
  staticFile,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export const promoDefaults = {
  kind: 'Торговое помещение',
  address: 'Сенницкий сельсовет, 68',
  area: 427,
  priceUsd: 555100,
  priceByn: '1 604 666 р.',
  phone: '+375 29 627-87-86',
  source: 'megapolis-real.by',
  photo: 'photo.png',
};

const GOLD = '#e8b93a';
const INK = '#f4ead2';
const FONT = 'Helvetica, Arial, sans-serif';

const spaced = (n: number) =>
  Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

export const RealtyPromo: React.FC<typeof promoDefaults> = (p) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  // Ken Burns: медленный наезд на фото
  const zoom = interpolate(frame, [0, durationInFrames], [1.06, 1.2]);

  // цена набегает от 0
  const price = interpolate(frame, [18, 78], [0, p.priceUsd], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // ступенчатый вылет строк снизу
  const rise = (delay: number) => {
    const s = spring({frame: frame - delay, fps, config: {damping: 200}});
    return {value: s, opacity: s, transform: `translateY(${(1 - s) * 45}px)`};
  };

  const phone = rise(66);
  const pulse = 1 + 0.04 * Math.sin((frame / fps) * 6);

  return (
    <AbsoluteFill style={{backgroundColor: '#0d0c0a'}}>
      <AbsoluteFill style={{transform: `scale(${zoom})`}}>
        <Img
          src={staticFile(p.photo)}
          style={{width: '100%', height: '100%', objectFit: 'cover'}}
        />
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(13,12,10,0.60) 0%, rgba(13,12,10,0.05) 30%, rgba(13,12,10,0.15) 52%, rgba(13,12,10,0.96) 100%)',
        }}
      />

      <AbsoluteFill
        style={{
          border: `${Math.round(
            interpolate(frame, [0, 20], [0, 10], {extrapolateRight: 'clamp'}),
          )}px solid ${GOLD}`,
          opacity: 0.85,
        }}
      />

      <div style={{position: 'absolute', top: 70, left: 70, ...styleOf(rise(6))}}>
        <span
          style={{
            background: GOLD,
            color: '#181206',
            fontWeight: 800,
            fontSize: 40,
            padding: '14px 30px',
            borderRadius: 999,
            letterSpacing: 1,
            fontFamily: FONT,
          }}
        >
          {p.kind.toUpperCase()}
        </span>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 70,
          right: 70,
          bottom: 90,
          fontFamily: FONT,
        }}
      >
        <div style={{...styleOf(rise(20)), color: GOLD, fontSize: 122, fontWeight: 900, lineHeight: 1}}>
          ${spaced(price)}
        </div>
        <div style={{...styleOf(rise(30)), color: INK, fontSize: 40, marginTop: 8, opacity: 0.85}}>
          {p.priceByn}
        </div>
        <div style={{...styleOf(rise(42)), color: INK, fontSize: 56, fontWeight: 700, marginTop: 28}}>
          {p.address}
        </div>
        <div style={{display: 'flex', gap: 20, marginTop: 26, ...styleOf(rise(54))}}>
          <span style={chip}>{p.area} м²</span>
          <span style={chip}>{p.source}</span>
        </div>
        <div
          style={{
            marginTop: 42,
            opacity: phone.opacity,
            transform: `translateY(${(1 - phone.value) * 45}px) scale(${pulse})`,
            transformOrigin: 'left center',
          }}
        >
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 18,
              background: 'rgba(232,185,58,0.15)',
              border: `3px solid ${GOLD}`,
              color: GOLD,
              fontSize: 60,
              fontWeight: 800,
              padding: '18px 40px',
              borderRadius: 20,
            }}
          >
            ☎ {p.phone}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const styleOf = (r: {opacity: number; transform: string}): React.CSSProperties => ({
  opacity: r.opacity,
  transform: r.transform,
});

const chip: React.CSSProperties = {
  background: 'rgba(244,234,210,0.12)',
  color: INK,
  fontSize: 38,
  fontWeight: 600,
  padding: '10px 26px',
  borderRadius: 14,
  border: '2px solid rgba(244,234,210,0.3)',
};

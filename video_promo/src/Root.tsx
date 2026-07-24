import React from 'react';
import {Composition} from 'remotion';
import {RealtyPromo, promoDefaults} from './Promo';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="RealtyPromo"
      component={RealtyPromo}
      durationInFrames={210}
      fps={30}
      width={1080}
      height={1350}
      defaultProps={promoDefaults}
    />
  );
};

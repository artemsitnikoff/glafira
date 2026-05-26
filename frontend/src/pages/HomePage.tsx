import { useState } from 'react';
import { useUiStore } from '@/store/uiStore';
import { HomeHeader } from './home/HomeHeader';
import { KpiGrid } from './home/KpiGrid';
import { AttentionList } from './home/AttentionList';
import { EventsFeed } from './home/EventsFeed';
import { PulseBlock } from './home/PulseBlock';
import { SourcesBlock } from './home/SourcesBlock';
import './HomePage.css';

export default function HomePage() {
  const [period, setPeriod] = useState('month');
  const { showSources } = useUiStore();

  return (
    <div className="home-page">
      <HomeHeader period={period} onPeriodChange={setPeriod} />
      <KpiGrid period={period} />
      <div className="home-grid-2">
        <AttentionList />
        <EventsFeed />
      </div>
      <PulseBlock />
      {showSources && <SourcesBlock period={period} />}
    </div>
  );
}
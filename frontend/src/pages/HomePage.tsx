import { useState } from 'react';
import { useUiStore } from '@/store/uiStore';
import { HomeHeader } from './home/HomeHeader';
import { KpiGrid } from './home/KpiGrid';
import { AttentionList } from './home/AttentionList';
import { EventsFeed } from './home/EventsFeed';
import { SourcesBlock } from './home/SourcesBlock';
import './HomePage.css';

export default function HomePage() {
  const [period, setPeriod] = useState('month');
  const { showSources } = useUiStore();

  return (
    <div className="content-inner">
      <HomeHeader period={period} onPeriodChange={setPeriod} />
      <KpiGrid period={period} />
      <div className="dash-grid-2">
        <AttentionList />
        <EventsFeed />
      </div>
      {showSources && <SourcesBlock period={period} />}
    </div>
  );
}
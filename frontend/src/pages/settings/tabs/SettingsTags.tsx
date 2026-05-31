import { Icon } from '@/components/ui/Icon';
import { PageHead, Card } from '../components/FormComponents';

const TAG_PALETTE = [
  { id: 'blue', color: '#2A8AF0', soft: '#EAF3FE' },
  { id: 'green', color: '#16A34A', soft: '#DEF5E5' },
  { id: 'yellow', color: '#E0A21A', soft: '#FFF1C8' },
  { id: 'red', color: '#DC4646', soft: '#FCE3E3' },
  { id: 'violet', color: '#7E5CF0', soft: '#ECE7FE' },
  { id: 'rose', color: '#E26B7E', soft: '#FBE5EA' },
  { id: 'teal', color: '#3FA3B3', soft: '#DDF1F4' },
  { id: 'gray', color: '#5B6573', soft: '#ECEFF2' },
];

const tags = [
  { name: 'Топ-кандидат', color: 'blue', used: 47, when: '12.03.26', by: 'Анна С.', desc: 'Кандидат, который точно заслуживает оффера' },
  { name: 'Готов к выходу', color: 'green', used: 12, when: '28.03.26', by: 'Иван П.', desc: 'Двухнедельная готовность или меньше' },
  { name: 'На испытательном', color: 'yellow', used: 8, when: '01.04.26', by: 'Анна С.', desc: '' },
  { name: 'Чёрный список', color: 'red', used: 23, when: '15.02.26', by: 'Анна С.', desc: 'Не предлагать на новые вакансии' },
  { name: 'Реферал', color: 'violet', used: 34, when: '08.01.26', by: 'Иван П.', desc: 'Пришёл по рекомендации сотрудника' },
  { name: 'Релокация', color: 'teal', used: 18, when: '22.02.26', by: 'Анна С.', desc: 'Готов к переезду' },
  { name: 'Junior', color: 'gray', used: 6, when: '04.04.26', by: 'Иван П.', desc: '' },
  { name: 'Senior+', color: 'rose', used: 11, when: '04.04.26', by: 'Иван П.', desc: '' },
];

export function SettingsTags() {
  const palette = Object.fromEntries(TAG_PALETTE.map(p => [p.id, p]));

  return (
    <div className="set-content-inner">
      <PageHead title="Справочник тегов"
        subtitle="Теги используются для маркировки кандидатов в общей базе. По ним можно фильтровать"/>

      <div className="info-banner">
        <Icon name="bell" size={16} />
        <div>
          <b>Скоро.</b> Функциональность находится в разработке.
        </div>
      </div>

      <Card>
        <div className="tags-toolbar">
          <div className="users-search">
            <Icon name="search" size={14}/>
            <input placeholder="Поиск тегов…" disabled />
          </div>
          <div style={{ flex: 1 }}/>
          <button className="btn btn-primary btn-sm" disabled>
            <Icon name="plus" size={14}/>Новый тег
          </button>
        </div>

        <div className="tags-table">
          <div className="tt-thead">
            <div>Тег</div>
            <div>Описание</div>
            <div style={{ textAlign: 'right' }}>Кандидатов</div>
            <div>Создан</div>
            <div>Создал</div>
            <div></div>
          </div>
          {tags.map((t, i) => {
            const p = palette[t.color];
            return (
              <div key={i} className="tt-row">
                <div>
                  <span className="tag-chip" style={{ background: p.soft, color: p.color }}>
                    <span className="tag-dot" style={{ background: p.color }}/>{t.name}
                  </span>
                </div>
                <div className="t-secondary tt-desc">{t.desc || <span className="muted">—</span>}</div>
                <div className="t-mono tt-num" style={{ textAlign: 'right' }}>{t.used}</div>
                <div className="t-mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>{t.when}</div>
                <div className="t-secondary">{t.by}</div>
                <div style={{ textAlign: 'right' }}>
                  <button className="row-icon-btn" disabled><Icon name="more" size={16}/></button>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Палитра">
        <div className="palette-row">
          {TAG_PALETTE.map(p => (
            <div key={p.id} className="palette-cell">
              <span className="tag-chip" style={{ background: p.soft, color: p.color }}>
                <span className="tag-dot" style={{ background: p.color }}/>{p.id}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
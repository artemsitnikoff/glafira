type Props = {
  dirty?: boolean;
};

export function FieldDot({ dirty }: Props) {
  if (!dirty) return null;

  return <span className="field-dot" aria-label="Поле изменено" />;
}
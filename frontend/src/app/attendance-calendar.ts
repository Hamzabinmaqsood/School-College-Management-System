export function attendanceMonth(value: string) {
  const [year, month] = value.split('-').map(Number);
  if (!year || !month || month < 1 || month > 12) return null;
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return {from_date: value + '-01', to_date: value + '-' + last};
}

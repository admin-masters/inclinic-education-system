type Props = { label:string; value:number };
export const MetricCard = ({label,value}:Props) => (
  <div className="p-4 bg-white shadow rounded text-center">
    <div className="text-2xl font-bold">{value}</div>
    <div className="text-sm text-gray-500">{label}</div>
  </div>
);
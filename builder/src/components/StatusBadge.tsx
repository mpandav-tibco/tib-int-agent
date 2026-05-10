interface Props { status: string }

const colours: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  ingesting: 'bg-yellow-100 text-yellow-700',
  ready: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
}

export function StatusBadge({ status }: Props) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${colours[status] ?? colours.draft}`}>
      <span className="size-1.5 rounded-full bg-current opacity-70" />
      {status}
    </span>
  )
}

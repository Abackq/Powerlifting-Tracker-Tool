'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

type TrainingSet = {
    set_number: number
    reps: number
    weight_value: number | null
    rpe: number | null
}

type SessionExercise = {
    id: string
    exercises: { name: string } | null
    training_log: TrainingSet[]
}

type Session = {
    id: string
    day_number: number | null
    session_exercises: SessionExercise[]
}

type Week = {
    id: string
    block: number
    week: number
    week_start_date: string
    week_end_date: string
    sessions: Session[]
}

export default function DashboardPage() {
    const router = useRouter()
    const [weeks, setWeeks] = useState<Week[]>([])
    const [loading, setLoading] = useState(true)

    async function handleSignOut() {
        const supabase = createClient()
        const { error } = await supabase.auth.signOut()

        if (!error) {
            router.push('/login')
        }
    }

    useEffect(() => {
        async function load() {
            const supabase = createClient()
            const { data, error } = await supabase
                .from("program_weeks")
                .select(`
                    id, block, week, week_start_date, week_end_date,
                    sessions (
                        id, day_number,
                        session_exercises (
                            id,
                            exercises ( name ),
                            training_log ( set_number, reps, weight_value, rpe )
                        )
                    )
                `)
                .order("block")
                .order("week")

            if (error) console.error(error)
            setWeeks((data ?? []) as Week[])
            setLoading(false)
        }
        load()
    }, [])

    const blockNumbers = [...new Set(weeks.map(w => w.block))]

    return (
        <div>
            <h1>WELCOME</h1>
            <button onClick={handleSignOut}>Sign Out</button>

            {loading && <p>Loading...</p>}

            {blockNumbers.map(b => {
                const blockWeeks = weeks.filter(w => w.block === b)
                return (
                    <details key={b}>
                        <summary>Block {b} ({blockWeeks.length} weeks)</summary>

                        {blockWeeks.map(w => (
                            <details key={w.id}>
                                <summary>Week {w.week}: {w.week_start_date} to {w.week_end_date}</summary>

                                {[...w.sessions]
                                    .sort((a, c) => (a.day_number ?? 0) - (c.day_number ?? 0))
                                    .map(s => (
                                        <details key={s.id}>
                                            <summary>Day {s.day_number}</summary>

                                            {s.session_exercises.map(se => (
                                                <div key={se.id}>
                                                    <strong>{se.exercises?.name ?? 'Unknown exercise'}</strong>
                                                    <ul>
                                                        {[...se.training_log]
                                                            .sort((a, c) => a.set_number - c.set_number)
                                                            .map(t => (
                                                                <li key={t.set_number}>
                                                                    Set {t.set_number}: {t.reps} reps at {t.weight_value ?? '—'} (RPE {t.rpe ?? '—'})
                                                                </li>
                                                            ))}
                                                    </ul>
                                                </div>
                                            ))}
                                        </details>
                                    ))}
                            </details>
                        ))}
                    </details>
                )
            })}
        </div>
    )
}
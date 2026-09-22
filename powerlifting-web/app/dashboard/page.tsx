'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

export default function DashboardPage() {
    const router = useRouter()

    async function handleSignOut() {
        const supabase = createClient()
        const { error } = await supabase.auth.signOut()

        if(!error) {
            router.push('/login')
        }
    }

    return(
    <div>
        <h1>WELCOME</h1>
        <button onClick={handleSignOut}>Sign Out</button>
    </div>
)
}

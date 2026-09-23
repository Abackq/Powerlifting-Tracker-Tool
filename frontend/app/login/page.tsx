'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function LoginPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const router = useRouter()

    async function handleLogin() {
        const supabase = createClient()
        const { data, error } = await supabase.auth.signInWithPassword({ 
            email: email, 
            password: password
        })
        console.log(data, error)

        if(!error) {
            const { data: { user } } = await supabase.auth.getUser()

            if (!user) {
                console.log('No user logged in')
                return
            }
            
            const { data: existingClient } = await supabase
                .from('clients')
                .select('id')
                .eq('auth_user_id', user.id)
                .maybeSingle()
            
            if (existingClient) {
                router.push('/dashboard')
            }
            else {
                router.push('/onboarding')
            }
        }
    }

    return(
        <div>
            <h1>Login</h1>
            <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
            />
            <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
            />
            <button onClick={handleLogin}>Login</button>
            <br />
            <Link href="/signup">Don't have an account? Sign Up</Link>
        </div>
    )
}
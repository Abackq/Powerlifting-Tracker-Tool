'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import Link from 'next/link'

export default function SignupPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')

    async function handleSignup() {
        console.log('URL:', process.env.NEXT_PUBLIC_SUPABASE_URL)
        const supabase = createClient()
        console.log('Email being sent:', JSON.stringify(email))
        const { data, error } = await supabase.auth.signUp({
            email: email,
            password: password,
            options: {
                emailRedirectTo: '${window.location.origin}/login'
            }
        })
        console.log(data, error)
    }
       
    return (
        <div>
            <h1>Sign Up</h1>
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
            <button onClick={handleSignup}>Sign Up</button>
            <br />
            <Link href="/login">Already have an account? Login</Link>
        </div>
    )
}
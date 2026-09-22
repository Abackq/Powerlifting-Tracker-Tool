'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

// TODO: define and export the component function
export default function OnboardingPage() {

    const [first_name, setFirstName] = useState('')
    const [last_name, setLastName] = useState('')
    const [gender, setGender] = useState('')
    const router = useRouter()

    // TODO: define an async function handleOnboarding
    async function handleOnboarding () {
        const supabase = createClient()
        const { data: { user } } = await supabase.auth.getUser()

        if (!user) {
            console.log('No user logged in')
            return
        }

        const { error } = await supabase
            .from('clients')
            .insert({
                auth_user_id: user.id,
                first_name: first_name,
                last_name: last_name,
                gender: gender
            })
            console.log(user, error)

            if (!error) {
                router.push('/dashboard')
            }
    }

    return (
        <div>
            <input
                type="text"
                value={first_name}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="First Name"
            />
            <input
                type="text"
                value={last_name}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Last Name"
            />
            <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
            >
                <option value="">Select...</option>
                <option value="M">Male</option>
                <option value="F">Female</option>
            </select>
            <button onClick={handleOnboarding}>Confirm</button>
        </div>
    )
}

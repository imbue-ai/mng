on_post_install be sure to ask the user which agent types they want to have default access to github (all/none/selected)

then for create/provision/limit, go get the data into the right place (ex: tokens, env vars, ssh keys, etc)

we probably need to be a little bit smart about *which* of those things we pull in, prompting the user for that, etc...

## TODOs

None of the GitHub auth functionality is currently implemented:

- Implement `on_post_install` hook (hook itself not yet implemented in plugin system)
- Create GitHub auth plugin with user prompting for agent type access configuration
- Implement token provisioning (GitHub PATs, GITHUB_TOKEN env var)
- Implement SSH key provisioning (~/.ssh/id_* keys)
- Implement env var injection during agent provisioning
- Add smart prompting for which credentials to provision (tokens/keys/both)
- Implement create/provision/limit logic for distributing credentials to agents

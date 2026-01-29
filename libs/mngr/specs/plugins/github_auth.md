on_post_install [future] be sure to ask the user which agent types they want to have default access to github (all/none/selected)

then for create/provision/limit, go get the data into the right place (ex: tokens, env vars, ssh keys, etc)

we probably need to be a little bit smart about *which* of those things we pull in, prompting the user for that, etc...

Note: The following features are planned but not yet implemented: GitHub auth plugin, token provisioning (GitHub PATs, GITHUB_TOKEN env var), SSH key provisioning, env var injection during agent provisioning, smart prompting for credential selection, create/provision/limit logic for distributing credentials to agents.

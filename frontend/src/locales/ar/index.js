// The Arabic catalogue, one file per group of screens (see docs/i18n.md for the groups and the glossary).
import shell from './shell.js'
import overview from './overview.js'
import trends from './trends.js'
import articles from './articles.js'
import outlets from './outlets.js'
import contribute from './contribute.js'
import ai from './ai.js'
import help from './help.js'

export default { ...help, ...ai, ...contribute, ...outlets, ...articles, ...trends, ...overview, ...shell }

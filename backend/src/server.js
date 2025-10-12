const app = require('./app')
const dotenv = require('dotenv');


require('dotenv').config({ path: '../../.env' });

const PORT =  process.env.PORT || 3000

app.listen(PORT, () => console.log(`✅ Server running on port ${PORT}`));

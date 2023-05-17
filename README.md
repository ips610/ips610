# Ishpuneet-Singh

fetch('https://hitcounter.pythonanywhere.com/count', {
    credentials: 'include'
})
    .then(res => res.text())
    .then(count => console.log('Count: ' + count))

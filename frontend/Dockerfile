FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

# ⚠️ Important : définir ARG avant ENV
ARG PORT=8080
ENV PORT=$PORT

EXPOSE $PORT

CMD ["npm","start"]

import { getMachineName } from "../../lib/identity.js"

export default function (RED) {
  function Node(config) {
    RED.nodes.createNode(this, config)
    const node = this
    node.on("input", function (msg, send, done) {
      getMachineName()
        .then((name) => {
          msg.payload ??= {}
          Object.assign(msg.payload, { name })
          send(msg)
          done()
        })
        .catch(done)
    })
  }

  RED.nodes.registerType("get name", Node)
}
